from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from db_utils.create_in_collection import create_user 
from db_utils.read_from_collection import get_all_users, get_user_by_id 
from db_utils.update_collection import update_user 
from db_utils.delete_from_collection import delete_user 

router = APIRouter()

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


@router.post("/users")
def create_new_user(data: UserCreate):
    result = create_user(data.dict())
    return {"message": "User created", "id": result["inserted_id"]}


@router.get("/users")
def list_users():
    return get_all_users()


@router.get("/users/{user_id}")
def get_one_user(user_id: str):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/users/{user_id}")
def update_user_data(user_id: str, data: UserCreate):
    result = update_user(user_id, data.dict())
    if result["modified_count"] == 0:
        raise HTTPException(status_code=404, detail="User not found or no change")
    return {"message": "User updated successfully"}


@router.delete("/users/{user_id}")
def remove_user(user_id: str):
    result = delete_user(user_id)
    if result["deleted_count"] == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted successfully"}
