from fastapi import APIRouter, Header, HTTPException
from typing import List, Optional
from pydantic import BaseModel, Field, validator
from datetime import datetime
from db_utils.get_connection import get_collection
from bson import ObjectId

router = APIRouter()

# -----------------------------
# Models
# -----------------------------

class TransactionCreate(BaseModel):
    type: str
    amount: float
    date: str  # Receiving as string YYYY-MM-DD or ISO
    category: str
    details: Optional[str] = None

    @validator('type')
    def validate_type(cls, v):
        if v not in ['income', 'expense']:
            raise ValueError("type must be 'income' or 'expense'")
        return v

    @validator('date')
    def validate_date(cls, v):
        try:
            # Check if valid ISO format or Date format
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")

class TransactionResponse(BaseModel):
    id: str = Field(alias="_id")
    user_id: str
    type: str
    amount: float
    date: str
    category: str
    details: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str
        }

# -----------------------------
# POST: Add transaction
# -----------------------------
@router.post("/", response_model=TransactionResponse)
async def add_transaction(
    transaction: TransactionCreate,
    user_id: str = Header(None)
):
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)

    try:
        # Convert date string to datetime for storage
        txn_date = datetime.fromisoformat(transaction.date)
    except ValueError:
        raise HTTPException(detail="Invalid date format", status_code=400)

    txn_data = {
        "user_id": user_id,
        "type": transaction.type,
        "amount": transaction.amount,
        "date": txn_date,
        "category": transaction.category,
        "details": transaction.details,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    collection = get_collection("users_transactions")
    result = await collection.insert_one(txn_data)

    # Prepare response
    txn_data["_id"] = str(result.inserted_id)
    # Check if date is datetime before calling date()
    if isinstance(txn_data["date"], datetime):
         txn_data["date"] = txn_data["date"].date().isoformat()

    return txn_data

# -----------------------------
# GET: Transactions for user
# -----------------------------
@router.get("/", response_model=List[TransactionResponse])
async def get_user_transactions(user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)

    collection = get_collection("users_transactions")
    transactions = []

    async for txn in collection.find({"user_id": user_id}).sort("date", -1):
        txn["_id"] = str(txn["_id"])
        txn["user_id"] = str(txn["user_id"])

        # Ensure date is returned as string YYYY-MM-DD
        date_val = txn.get("date")
        if isinstance(date_val, datetime):
            txn["date"] = date_val.date().isoformat()
        elif isinstance(date_val, str):
            # If it's already a string, keep it (legacy data might be different)
            txn["date"] = date_val

        transactions.append(txn)

    return transactions

@router.put("/{transaction_id}")
async def update_transaction(
    transaction_id: str,
    payload: TransactionCreate,
    user_id: str = Header(None)
):
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID missing")

    collection = get_collection("users_transactions")

    result = await collection.update_one(
        {
            "_id": ObjectId(transaction_id),
            "user_id": user_id
        },
        {
            "$set": {
                "type": payload.type,
                "amount": payload.amount,
                "date": datetime.fromisoformat(payload.date),
                "category": payload.category,
                "details": payload.details,
                "updated_at": datetime.utcnow()
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {"message": "Transaction updated successfully"}

@router.delete("/{transaction_id}")
async def delete_transaction(
    transaction_id: str,
    user_id: str = Header(None)
):
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID missing")

    collection = get_collection("users_transactions")

    result = await collection.delete_one({
        "_id": ObjectId(transaction_id),
        "user_id": user_id
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {"message": "Transaction deleted successfully"}
