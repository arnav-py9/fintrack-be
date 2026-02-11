from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import List
from db_utils.get_connection import get_collection
from bson import ObjectId

router = APIRouter()

# -------------------- MODELS --------------------

class ProfitCreate(BaseModel):
    amount: float
    date: str
    details: str | None = None


# -------------------- POST: ADD PROFIT --------------------
@router.post("/")
async def add_profit(
    data: ProfitCreate,
    user_id: str = Header(None)
):
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID missing")

    try:
        profit_date = datetime.fromisoformat(data.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    collection = get_collection("users_business_profit")

    profit = {
        "user_id": ObjectId(user_id),
        "amount": data.amount,
        "date": profit_date,
        "details": data.details,
        "created_at": datetime.utcnow()
    }

    await collection.insert_one(profit)

    return {"message": "Profit entry added"}


# -------------------- GET: FETCH PROFITS --------------------
@router.get("/")
async def get_profits(user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID missing")

    collection = get_collection("users_business_profit")

    profits = await collection.find({"user_id": ObjectId(user_id)}).to_list(length=None)

    total_profit = 0
    current_month_profit = 0
    now = datetime.utcnow()

    for p in profits:
        total_profit += p["amount"]
        if p["date"].month == now.month and p["date"].year == now.year:
            current_month_profit += p["amount"]

    avg_profit = total_profit / len(profits) if profits else 0

    # serialize
    for p in profits:
        p["_id"] = str(p["_id"])
        p["user_id"] = str(p["user_id"])
        p["date"] = p["date"].date().isoformat()

    return {
        "total_profit": total_profit,
        "this_month_profit": current_month_profit,
        "average_profit": round(avg_profit, 2),
        "entries": profits
    }