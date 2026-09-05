from datetime import datetime
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from db_utils.get_connection import get_collection


router = APIRouter()

BatchStatus = Literal["draft", "active", "completed", "ended_early", "settled", "cancelled"]
Account = Literal["Business", "Personal", "Slice", "Other"]


class ClientCreate(BaseModel):
    name: str = Field(min_length=1)
    contactName: Optional[str] = ""
    contactEmail: Optional[str] = ""
    contactPhone: Optional[str] = ""
    notes: Optional[str] = ""


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    contactName: Optional[str] = None
    contactEmail: Optional[str] = None
    contactPhone: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[Literal["active", "inactive"]] = None


class BatchCreate(BaseModel):
    clientId: str
    batchName: str = Field(min_length=1)
    committedVideos: int = Field(gt=0)
    committedValue: float = Field(gt=0)
    startDate: str
    expectedEndDate: Optional[str] = ""
    notes: Optional[str] = ""


class BatchUpdate(BaseModel):
    clientId: Optional[str] = None
    batchName: Optional[str] = Field(default=None, min_length=1)
    committedVideos: Optional[int] = Field(default=None, gt=0)
    committedValue: Optional[float] = Field(default=None, gt=0)
    startDate: Optional[str] = None
    expectedEndDate: Optional[str] = None
    notes: Optional[str] = None


class PaymentCreate(BaseModel):
    batchId: str
    amount: float = Field(gt=0)
    date: str
    receivedIn: Account = "Business"
    notes: Optional[str] = ""


class DeliveryCreate(BaseModel):
    batchId: str
    videosCompleted: int = Field(gt=0)
    date: str
    notes: Optional[str] = ""


class SettlementCreate(BaseModel):
    batchId: str
    amount: float = Field(gt=0)
    date: str
    fromAccount: Account = "Business"
    toAccount: Account = "Personal"
    notes: Optional[str] = ""


class EndBatchRequest(BaseModel):
    reason: str = Field(min_length=1)


def _require_user(user_id: Optional[str]) -> str:
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)
    return user_id


def _as_object_id(value: str, field_name: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(detail=f"Invalid {field_name}", status_code=400)
    return ObjectId(value)


def _serialize(doc: dict) -> dict:
    result = dict(doc)
    result["id"] = str(result.pop("_id"))
    result.pop("user_id", None)
    return result


async def _owned_client(client_id: str, user_id: str) -> dict:
    client = await get_collection("client_revenue_clients").find_one(
        {"_id": _as_object_id(client_id, "client ID"), "user_id": user_id}
    )
    if not client:
        raise HTTPException(detail="Client not found", status_code=404)
    return client


async def _owned_batch(batch_id: str, user_id: str) -> dict:
    batch = await get_collection("client_revenue_batches").find_one(
        {"_id": _as_object_id(batch_id, "batch ID"), "user_id": user_id}
    )
    if not batch:
        raise HTTPException(detail="Batch not found", status_code=404)
    return batch


async def _sum_field(collection_name: str, query: dict, field_name: str) -> float:
    docs = await get_collection(collection_name).find(query).to_list(length=None)
    return sum(doc.get(field_name, 0) for doc in docs)


async def _ensure_no_other_active_batch(
    user_id: str, client_id: str, exclude_batch_id: Optional[ObjectId] = None
) -> None:
    query = {"user_id": user_id, "clientId": client_id, "status": "active"}
    if exclude_batch_id:
        query["_id"] = {"$ne": exclude_batch_id}
    if await get_collection("client_revenue_batches").find_one(query):
        raise HTTPException(
            detail="This client already has an active batch. Complete or end it first.",
            status_code=409,
        )


@router.get("/")
async def get_client_revenue_data(user_id: str = Header(None)):
    user_id = _require_user(user_id)
    collections = {
        "clients": ("client_revenue_clients", "createdAt"),
        "batches": ("client_revenue_batches", "createdAt"),
        "payments": ("client_revenue_payments", "date"),
        "deliveries": ("client_revenue_deliveries", "date"),
        "settlements": ("client_revenue_settlements", "date"),
    }
    result = {}
    for response_key, (collection_name, sort_key) in collections.items():
        docs = await get_collection(collection_name).find(
            {"user_id": user_id}
        ).sort(sort_key, -1).to_list(length=None)
        result[response_key] = [_serialize(doc) for doc in docs]
    return result


@router.post("/clients", status_code=201)
async def add_client(data: ClientCreate, user_id: str = Header(None)):
    user_id = _require_user(user_id)
    doc = {
        "user_id": user_id,
        "name": data.name.strip(),
        "contactName": data.contactName,
        "contactEmail": data.contactEmail,
        "contactPhone": data.contactPhone,
        "status": "active",
        "notes": data.notes,
        "createdAt": datetime.utcnow().date().isoformat(),
    }
    if not doc["name"]:
        raise HTTPException(detail="Client name is required", status_code=400)
    result = await get_collection("client_revenue_clients").insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


@router.put("/clients/{client_id}")
async def update_client(client_id: str, data: ClientUpdate, user_id: str = Header(None)):
    user_id = _require_user(user_id)
    object_id = _as_object_id(client_id, "client ID")
    await _owned_client(client_id, user_id)
    updates = data.model_dump(exclude_none=True)
    if "name" in updates:
        updates["name"] = updates["name"].strip()
        if not updates["name"]:
            raise HTTPException(detail="Client name is required", status_code=400)
    if updates:
        updates["updatedAt"] = datetime.utcnow().date().isoformat()
        await get_collection("client_revenue_clients").update_one(
            {"_id": object_id, "user_id": user_id}, {"$set": updates}
        )
    return _serialize(
        await get_collection("client_revenue_clients").find_one(
            {"_id": object_id, "user_id": user_id}
        )
    )


@router.delete("/clients/{client_id}")
async def archive_client(client_id: str, user_id: str = Header(None)):
    user_id = _require_user(user_id)
    object_id = _as_object_id(client_id, "client ID")
    await _owned_client(client_id, user_id)
    active_batch = await get_collection("client_revenue_batches").find_one(
        {"user_id": user_id, "clientId": client_id, "status": "active"}
    )
    if active_batch:
        raise HTTPException(detail="End the active batch before archiving this client", status_code=409)
    await get_collection("client_revenue_clients").update_one(
        {"_id": object_id, "user_id": user_id},
        {"$set": {"status": "inactive", "updatedAt": datetime.utcnow().date().isoformat()}},
    )
    return {"message": "Client archived"}


@router.post("/batches", status_code=201)
async def add_batch(data: BatchCreate, user_id: str = Header(None)):
    user_id = _require_user(user_id)
    client = await _owned_client(data.clientId, user_id)
    if client.get("status") != "active":
        raise HTTPException(detail="Cannot create a batch for an inactive client", status_code=409)
    await _ensure_no_other_active_batch(user_id, data.clientId)
    doc = {
        "user_id": user_id,
        "clientId": data.clientId,
        "batchName": data.batchName.strip(),
        "committedVideos": data.committedVideos,
        "committedValue": data.committedValue,
        "startDate": data.startDate,
        "expectedEndDate": data.expectedEndDate,
        "status": "active",
        "notes": data.notes,
        "createdAt": datetime.utcnow().date().isoformat(),
    }
    if not doc["batchName"]:
        raise HTTPException(detail="Batch name is required", status_code=400)
    result = await get_collection("client_revenue_batches").insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


@router.put("/batches/{batch_id}")
async def update_batch(batch_id: str, data: BatchUpdate, user_id: str = Header(None)):
    user_id = _require_user(user_id)
    object_id = _as_object_id(batch_id, "batch ID")
    batch = await _owned_batch(batch_id, user_id)
    updates = data.model_dump(exclude_none=True)
    target_client_id = updates.get("clientId", batch["clientId"])
    if target_client_id != batch["clientId"]:
        client = await _owned_client(target_client_id, user_id)
        if client.get("status") != "active":
            raise HTTPException(detail="Cannot move a batch to an inactive client", status_code=409)
    if batch.get("status") == "active":
        await _ensure_no_other_active_batch(user_id, target_client_id, object_id)
    delivered = await _sum_field(
        "client_revenue_deliveries", {"user_id": user_id, "batchId": batch_id}, "videosCompleted"
    )
    if updates.get("committedVideos", batch["committedVideos"]) < delivered:
        raise HTTPException(detail="Committed videos cannot be lower than videos already delivered", status_code=409)
    if "batchName" in updates:
        updates["batchName"] = updates["batchName"].strip()
        if not updates["batchName"]:
            raise HTTPException(detail="Batch name is required", status_code=400)
    if updates:
        updates["updatedAt"] = datetime.utcnow().date().isoformat()
        await get_collection("client_revenue_batches").update_one(
            {"_id": object_id, "user_id": user_id}, {"$set": updates}
        )
    return _serialize(
        await get_collection("client_revenue_batches").find_one(
            {"_id": object_id, "user_id": user_id}
        )
    )


@router.delete("/batches/{batch_id}")
async def cancel_batch(batch_id: str, user_id: str = Header(None)):
    user_id = _require_user(user_id)
    object_id = _as_object_id(batch_id, "batch ID")
    await _owned_batch(batch_id, user_id)
    has_activity = False
    for collection_name in (
        "client_revenue_payments",
        "client_revenue_deliveries",
        "client_revenue_settlements",
    ):
        if await get_collection(collection_name).find_one({"user_id": user_id, "batchId": batch_id}):
            has_activity = True
            break
    if has_activity:
        raise HTTPException(detail="A batch with activity cannot be cancelled; end it instead", status_code=409)
    await get_collection("client_revenue_batches").update_one(
        {"_id": object_id, "user_id": user_id},
        {"$set": {"status": "cancelled", "updatedAt": datetime.utcnow().date().isoformat()}},
    )
    return {"message": "Batch cancelled"}


@router.post("/payments", status_code=201)
async def add_payment(data: PaymentCreate, user_id: str = Header(None)):
    user_id = _require_user(user_id)
    await _owned_batch(data.batchId, user_id)
    doc = {
        "user_id": user_id,
        "batchId": data.batchId,
        "amount": data.amount,
        "date": data.date,
        "receivedIn": data.receivedIn,
        "notes": data.notes,
    }
    result = await get_collection("client_revenue_payments").insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


@router.post("/deliveries", status_code=201)
async def add_delivery(data: DeliveryCreate, user_id: str = Header(None)):
    user_id = _require_user(user_id)
    batch = await _owned_batch(data.batchId, user_id)
    if batch.get("status") != "active":
        raise HTTPException(detail="Deliveries can only be added to an active batch", status_code=409)
    delivered = await _sum_field(
        "client_revenue_deliveries",
        {"user_id": user_id, "batchId": data.batchId},
        "videosCompleted",
    )
    new_total = delivered + data.videosCompleted
    if new_total > batch["committedVideos"]:
        raise HTTPException(
            detail=f"Cannot exceed committed videos ({batch['committedVideos']}).",
            status_code=409,
        )
    doc = {
        "user_id": user_id,
        "batchId": data.batchId,
        "videosCompleted": data.videosCompleted,
        "date": data.date,
        "notes": data.notes,
    }
    result = await get_collection("client_revenue_deliveries").insert_one(doc)
    doc["_id"] = result.inserted_id
    if new_total == batch["committedVideos"]:
        await get_collection("client_revenue_batches").update_one(
            {"_id": batch["_id"], "user_id": user_id},
            {"$set": {"status": "completed", "completedAt": data.date}},
        )
    return _serialize(doc)


@router.post("/settlements", status_code=201)
async def add_settlement(data: SettlementCreate, user_id: str = Header(None)):
    user_id = _require_user(user_id)
    batch = await _owned_batch(data.batchId, user_id)
    if data.fromAccount == data.toAccount:
        raise HTTPException(detail="Settlement accounts must be different", status_code=400)
    delivered = await _sum_field(
        "client_revenue_deliveries",
        {"user_id": user_id, "batchId": data.batchId},
        "videosCompleted",
    )
    settled = await _sum_field(
        "client_revenue_settlements",
        {"user_id": user_id, "batchId": data.batchId},
        "amount",
    )
    earned = delivered * (batch["committedValue"] / batch["committedVideos"])
    if settled + data.amount > earned:
        raise HTTPException(detail="Settlement cannot exceed unsettled earned revenue", status_code=409)
    doc = {
        "user_id": user_id,
        "batchId": data.batchId,
        "amount": data.amount,
        "date": data.date,
        "fromAccount": data.fromAccount,
        "toAccount": data.toAccount,
        "notes": data.notes,
    }
    result = await get_collection("client_revenue_settlements").insert_one(doc)
    doc["_id"] = result.inserted_id
    if settled + data.amount == earned and batch.get("status") == "completed":
        await get_collection("client_revenue_batches").update_one(
            {"_id": batch["_id"], "user_id": user_id}, {"$set": {"status": "settled"}}
        )
    return _serialize(doc)


@router.patch("/batches/{batch_id}/complete")
async def complete_batch(batch_id: str, user_id: str = Header(None)):
    user_id = _require_user(user_id)
    batch = await _owned_batch(batch_id, user_id)
    if batch.get("status") != "active":
        raise HTTPException(detail="Only an active batch can be completed", status_code=409)
    delivered = await _sum_field(
        "client_revenue_deliveries", {"user_id": user_id, "batchId": batch_id}, "videosCompleted"
    )
    if delivered != batch["committedVideos"]:
        raise HTTPException(detail="All committed videos must be delivered first", status_code=409)
    await get_collection("client_revenue_batches").update_one(
        {"_id": batch["_id"], "user_id": user_id},
        {"$set": {"status": "completed", "completedAt": datetime.utcnow().date().isoformat()}},
    )
    return _serialize(await _owned_batch(batch_id, user_id))


@router.patch("/batches/{batch_id}/end")
async def end_batch(batch_id: str, data: EndBatchRequest, user_id: str = Header(None)):
    user_id = _require_user(user_id)
    batch = await _owned_batch(batch_id, user_id)
    if batch.get("status") != "active":
        raise HTTPException(detail="Only an active batch can be ended early", status_code=409)
    reason = data.reason.strip()
    if not reason:
        raise HTTPException(detail="An end reason is required", status_code=400)
    await get_collection("client_revenue_batches").update_one(
        {"_id": batch["_id"], "user_id": user_id},
        {"$set": {"status": "ended_early", "endedEarlyReason": reason}},
    )
    return _serialize(await _owned_batch(batch_id, user_id))
