from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from db_utils.get_connection import get_collection
from bson import ObjectId

router = APIRouter()

# -----------------------------
# Models
# -----------------------------

class ClientCreate(BaseModel):
    name: str
    contactName: Optional[str] = ""
    contactEmail: Optional[str] = ""
    contactPhone: Optional[str] = ""
    notes: Optional[str] = ""


class BatchCreate(BaseModel):
    clientId: str
    batchName: str
    committedVideos: int
    committedValue: float
    startDate: str
    expectedEndDate: Optional[str] = ""
    notes: Optional[str] = ""


class PaymentCreate(BaseModel):
    batchId: str
    amount: float
    date: str
    receivedIn: Optional[str] = "Business"
    notes: Optional[str] = ""


class DeliveryCreate(BaseModel):
    batchId: str
    videosCompleted: int
    date: str
    notes: Optional[str] = ""


class SettlementCreate(BaseModel):
    batchId: str
    amount: float
    date: str
    fromAccount: Optional[str] = "Business"
    toAccount: Optional[str] = "Personal"
    notes: Optional[str] = ""


class EndBatchRequest(BaseModel):
    reason: str


# -----------------------------
# Helpers
# -----------------------------

def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    doc.pop("user_id", None)
    return doc


# -----------------------------
# GET: All client-revenue data for the user
# -----------------------------
@router.get("/")
async def get_client_revenue_data(user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)

    clients = get_collection("client_revenue_clients")
    batches = get_collection("client_revenue_batches")
    payments = get_collection("client_revenue_payments")
    deliveries = get_collection("client_revenue_deliveries")
    settlements = get_collection("client_revenue_settlements")

    return {
        "clients": [_serialize(c) for c in await clients.find({"user_id": user_id}).sort("createdAt", -1).to_list(length=None)],
        "batches": [_serialize(b) for b in await batches.find({"user_id": user_id}).sort("createdAt", -1).to_list(length=None)],
        "payments": [_serialize(p) for p in await payments.find({"user_id": user_id}).sort("date", -1).to_list(length=None)],
        "deliveries": [_serialize(d) for d in await deliveries.find({"user_id": user_id}).sort("date", -1).to_list(length=None)],
        "settlements": [_serialize(s) for s in await settlements.find({"user_id": user_id}).sort("date", -1).to_list(length=None)],
    }


# -----------------------------
# POST: Add client
# -----------------------------
@router.post("/clients")
async def add_client(data: ClientCreate, user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)

    doc = {
        "user_id": user_id,
        "name": data.name,
        "contactName": data.contactName,
        "contactEmail": data.contactEmail,
        "contactPhone": data.contactPhone,
        "status": "active",
        "notes": data.notes,
        "createdAt": datetime.utcnow().date().isoformat(),
    }

    collection = get_collection("client_revenue_clients")
    result = await collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


# -----------------------------
# POST: Add batch
# -----------------------------
@router.post("/batches")
async def add_batch(data: BatchCreate, user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)

    if data.committedVideos <= 0:
        raise HTTPException(detail="Committed videos must be greater than 0", status_code=400)
    if data.committedValue <= 0:
        raise HTTPException(detail="Committed value must be greater than 0", status_code=400)

    collection = get_collection("client_revenue_batches")

    existing_active = await collection.find_one({
        "user_id": user_id,
        "clientId": data.clientId,
        "status": "active",
    })
    if existing_active:
        raise HTTPException(
            detail="This client already has an active batch. Complete or end it first.",
            status_code=400,
        )

    doc = {
        "user_id": user_id,
        "clientId": data.clientId,
        "batchName": data.batchName,
        "committedVideos": data.committedVideos,
        "committedValue": data.committedValue,
        "startDate": data.startDate,
        "expectedEndDate": data.expectedEndDate,
        "status": "active",
        "notes": data.notes,
        "createdAt": datetime.utcnow().date().isoformat(),
    }

    result = await collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


# -----------------------------
# POST: Add payment
# -----------------------------
@router.post("/payments")
async def add_payment(data: PaymentCreate, user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)

    if data.amount <= 0:
        raise HTTPException(detail="Amount must be greater than 0", status_code=400)

    doc = {
        "user_id": user_id,
        "batchId": data.batchId,
        "amount": data.amount,
        "date": data.date,
        "receivedIn": data.receivedIn,
        "notes": data.notes,
    }

    collection = get_collection("client_revenue_payments")
    result = await collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


# -----------------------------
# POST: Add delivery log
# -----------------------------
@router.post("/deliveries")
async def add_delivery(data: DeliveryCreate, user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)

    if data.videosCompleted <= 0:
        raise HTTPException(detail="Videos completed must be greater than 0", status_code=400)

    batches = get_collection("client_revenue_batches")
    batch = await batches.find_one({"_id": ObjectId(data.batchId), "user_id": user_id})
    if not batch:
        raise HTTPException(detail="Batch not found", status_code=404)

    deliveries = get_collection("client_revenue_deliveries")
    existing = await deliveries.find({"user_id": user_id, "batchId": data.batchId}).to_list(length=None)
    already_delivered = sum(d["videosCompleted"] for d in existing)

    if already_delivered + data.videosCompleted > batch["committedVideos"]:
        raise HTTPException(
            detail=f"Cannot exceed committed videos ({batch['committedVideos']}).",
            status_code=400,
        )

    doc = {
        "user_id": user_id,
        "batchId": data.batchId,
        "videosCompleted": data.videosCompleted,
        "date": data.date,
        "notes": data.notes,
    }

    result = await deliveries.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


# -----------------------------
# POST: Add settlement
# -----------------------------
@router.post("/settlements")
async def add_settlement(data: SettlementCreate, user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)

    if data.amount <= 0:
        raise HTTPException(detail="Amount must be greater than 0", status_code=400)

    doc = {
        "user_id": user_id,
        "batchId": data.batchId,
        "amount": data.amount,
        "date": data.date,
        "fromAccount": data.fromAccount,
        "toAccount": data.toAccount,
        "notes": data.notes,
    }

    collection = get_collection("client_revenue_settlements")
    result = await collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


# -----------------------------
# PATCH: End batch early
# -----------------------------
@router.patch("/batches/{batch_id}/end")
async def end_batch(batch_id: str, data: EndBatchRequest, user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)

    collection = get_collection("client_revenue_batches")
    result = await collection.update_one(
        {"_id": ObjectId(batch_id), "user_id": user_id},
        {"$set": {"status": "ended_early", "endedEarlyReason": data.reason}},
    )

    if result.matched_count == 0:
        raise HTTPException(detail="Batch not found", status_code=404)

    doc = await collection.find_one({"_id": ObjectId(batch_id), "user_id": user_id})
    return _serialize(doc)
