from fastapi import APIRouter, Header, HTTPException
from bson import ObjectId
from db_utils.get_connection import get_collection

router = APIRouter()


@router.get("/")
async def get_user_finances(user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)

    finances = get_collection("users_finances")
    data = await finances.find_one({"user_id": user_id})

    if not data:
        raise HTTPException(detail="User finance data not found", status_code=404)

    data["_id"] = str(data["_id"])
    data["user_id"] = str(data["user_id"])

    return data


@router.put("/")
async def update_user_finances(data: dict, user_id: str = Header(None)):
    if not user_id:
        raise HTTPException(detail="User ID missing", status_code=400)

    finances = get_collection("users_finances")

    # Remove _id if present to avoid Mongo write errors
    if "_id" in data:
        del data["_id"]

    result = await finances.update_one({"user_id": user_id}, {"$set": data})

    if result.matched_count == 0:
        raise HTTPException(detail="User finance data not found", status_code=404)

    return data
