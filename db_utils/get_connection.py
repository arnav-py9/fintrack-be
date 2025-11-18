import os
from dotenv import load_dotenv
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
MONGO_URL = os.getenv("MONGO_URL")
DB_NAME = os.getenv("DB_NAME", "fintrack")


# -------------------------
# LOCAL → SYNC (PyMongo)
# -------------------------
if ENVIRONMENT == "local":
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]

    def get_collection(collection_name: str):
        return db[collection_name]

else:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    def get_collection(collection_name: str):
        return db[collection_name]
