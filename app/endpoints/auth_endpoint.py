from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from datetime import datetime
from passlib.hash import bcrypt # type: ignore
from db_utils.get_connection import get_collection # type: ignore

router = APIRouter()

class SignupRequest(BaseModel):
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/auth/signup")
def signup(data: SignupRequest):
    users = get_collection("users")

    existing = users.find_one({"email": data.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    user = {
        "email": data.email,
        "password": data.password,
        "created_at": datetime.utcnow()
    }

    result = users.insert_one(user)
    return {"message": "Signup successful", "id": str(result.inserted_id)}



@router.post("/auth/login")
def login(data: LoginRequest):
    users = get_collection("users")

    user = users.find_one({"email": data.email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check password
    if not data.password==user["password"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )

    return {
        "message": "Login successful",
        "email": user["email"]
    }
