from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime
from db_utils.get_connection import get_collection
from bson import ObjectId

router = APIRouter()

# -------------------- MODELS --------------------

FOUNDERS = ["Utkarsh", "Umang"]

class FounderTransactionCreate(BaseModel):
    type: str  # "reimbursement" or "salary"
    amount: float
    date: str  # YYYY-MM-DD or ISO
    paid_by: Optional[str] = None
    paid_to: Optional[str] = None
    payee: Optional[str] = None

    @validator('type')
    def validate_type(cls, v):
        if v not in ['reimbursement', 'salary']:
            raise ValueError("type must be 'reimbursement' or 'salary'")
        return v

    @validator('date')
    def validate_date(cls, v):
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")

    @validator('paid_by')
    def validate_paid_by(cls, v, values):
        if values.get('type') == 'reimbursement' and not v:
            raise ValueError("paid_by is required for reimbursement")
        if v and v not in FOUNDERS:
            raise ValueError(f"paid_by must be one of {FOUNDERS}")
        return v

    @validator('paid_to')
    def validate_paid_to(cls, v, values):
        if values.get('type') == 'reimbursement' and not v:
            raise ValueError("paid_to is required for reimbursement")
        if v and v not in FOUNDERS:
            raise ValueError(f"paid_to must be one of {FOUNDERS}")
        return v

    @validator('payee')
    def validate_payee(cls, v, values):
        if values.get('type') == 'salary' and not v:
            raise ValueError("payee is required for salary")
        if v and v not in FOUNDERS:
            raise ValueError(f"payee must be one of {FOUNDERS}")
        return v


# -------------------- POST: ADD TRANSACTION --------------------
@router.post("/")
async def add_founder_transaction(
    data: FounderTransactionCreate,
    user_id: str = Header(None)
):
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID missing")

    try:
        txn_date = datetime.fromisoformat(data.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    txn = {
        "user_id": user_id,
        "type": data.type,
        "amount": data.amount,
        "date": txn_date,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    if data.type == "reimbursement":
        txn["paid_by"] = data.paid_by
        txn["paid_to"] = data.paid_to
    else:
        txn["payee"] = data.payee

    collection = get_collection("founders_transactions")
    await collection.insert_one(txn)

    return {"message": "Transaction added"}


# -------------------- GET: FETCH ALL + STATS --------------------
@router.get("/")
async def get_founder_transactions(user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID missing")

    # 1. Fetch founders_transactions
    ft_collection = get_collection("founders_transactions")
    founder_txns = await ft_collection.find({"user_id": user_id}).sort("date", -1).to_list(length=None)

    # 2. Fetch investment totals from users_transactions (expenses where payee is a founder)
    ut_collection = get_collection("users_transactions")
    user_txns = await ut_collection.find({
        "user_id": user_id,
        "type": "expense",
        "payee": {"$in": FOUNDERS}
    }).to_list(length=None)

    # 3. Compute per-founder stats
    summary = {}
    for founder in FOUNDERS:
        total_invested = sum(
            t["amount"] for t in user_txns if t.get("payee") == founder
        )
        reimbursements_received = sum(
            t["amount"] for t in founder_txns
            if t["type"] == "reimbursement" and t.get("paid_to") == founder
        )
        reimbursements_made = sum(
            t["amount"] for t in founder_txns
            if t["type"] == "reimbursement" and t.get("paid_by") == founder
        )
        salary_taken = sum(
            t["amount"] for t in founder_txns
            if t["type"] == "salary" and t.get("payee") == founder
        )
        # Effective contribution = total invested - reimbursements received
        # Exact payment (total out-of-pocket) = effective contribution + reimbursements made
        exact_payment = total_invested - reimbursements_received + reimbursements_made
        # Positive net = taken out more salary than total out-of-pocket
        net_contribution = salary_taken - exact_payment

        summary[founder] = {
            "total_invested": round(total_invested, 2),
            "reimbursements_received": round(reimbursements_received, 2),
            "reimbursements_made": round(reimbursements_made, 2),
            "salary_taken": round(salary_taken, 2),
            "exact_payment": round(exact_payment, 2),
            "net_contribution": round(net_contribution, 2)
        }

    # 4. Serialize and split into reimbursements / salaries
    reimbursements = []
    salaries = []

    for t in founder_txns:
        t["_id"] = str(t["_id"])
        if isinstance(t["date"], datetime):
            t["date"] = t["date"].date().isoformat()

        if t["type"] == "reimbursement":
            reimbursements.append(t)
        else:
            salaries.append(t)

    return {
        "founders_summary": summary,
        "reimbursements": reimbursements,
        "salaries": salaries
    }


# -------------------- PUT: UPDATE TRANSACTION --------------------
@router.put("/{transaction_id}")
async def update_founder_transaction(
    transaction_id: str,
    data: FounderTransactionCreate,
    user_id: str = Header(None)
):
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID missing")

    try:
        txn_date = datetime.fromisoformat(data.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    update_data = {
        "type": data.type,
        "amount": data.amount,
        "date": txn_date,
        "updated_at": datetime.utcnow()
    }

    if data.type == "reimbursement":
        update_data["paid_by"] = data.paid_by
        update_data["paid_to"] = data.paid_to
        update_data["payee"] = None
    else:
        update_data["payee"] = data.payee
        update_data["paid_by"] = None
        update_data["paid_to"] = None

    collection = get_collection("founders_transactions")
    result = await collection.update_one(
        {"_id": ObjectId(transaction_id), "user_id": user_id},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {"message": "Transaction updated successfully"}


# -------------------- DELETE: REMOVE TRANSACTION --------------------
@router.delete("/{transaction_id}")
async def delete_founder_transaction(
    transaction_id: str,
    user_id: str = Header(None)
):
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID missing")

    collection = get_collection("founders_transactions")
    result = await collection.delete_one({
        "_id": ObjectId(transaction_id),
        "user_id": user_id
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {"message": "Transaction deleted successfully"}
