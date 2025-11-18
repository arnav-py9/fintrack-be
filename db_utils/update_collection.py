from db_utils.get_connection import get_collection 
from bson import ObjectId

def update_user(user_id: str, data: dict):
    collection = get_collection("users")
    result = collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": data}
    )
    return {"modified_count": result.modified_count}
