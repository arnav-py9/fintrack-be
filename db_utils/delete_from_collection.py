from db_utils.get_connection import get_collection
from bson import ObjectId

async def delete_user(user_id: str):
    collection = get_collection("users")
    result = await collection.delete_one({"_id": ObjectId(user_id)})
    return {"deleted_count": result.deleted_count}
