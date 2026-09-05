import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")
DB_NAME = os.getenv("DB_NAME", "fintrack")

# Every endpoint uses Motor's async collection API, so local and production
# must expose the same interface.
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


def get_collection(collection_name: str):
    return db[collection_name]
