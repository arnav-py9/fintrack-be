from db_utils.get_connection import get_collection

async def create_user(data: dict):
    collection = get_collection("users")
    result = await collection.insert_one(data)
    return {"inserted_id": str(result.inserted_id)}
