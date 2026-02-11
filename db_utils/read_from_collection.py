from db_utils.get_connection import get_collection
from bson import ObjectId

async def get_all_users():
    collection = get_collection("users")
    users = []
    async for user in collection.find():
        user["_id"] = str(user["_id"])
        users.append(user)
    return users

async def get_user_by_id(user_id: str):
    collection = get_collection("users")
    user = await collection.find_one({"_id": ObjectId(user_id)})
    if user:
        user["_id"] = str(user["_id"])
    return user
