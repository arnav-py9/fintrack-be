from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from datetime import datetime
from passlib.hash import sha256_crypt
from db_utils.get_connection import get_collection  # type: ignore

router = APIRouter()

# -------------------- SCHEMAS --------------------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# -------------------- SIGNUP --------------------
@router.post("/signup")
async def signup(data: SignupRequest):
    users = get_collection("users")
    finances = get_collection("users_finances")

    if await users.find_one({"email": data.email}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # ✅ SAFE HASH (NO BCRYPT)
    hashed_password = sha256_crypt.hash(data.password)

    user = {
        "email": data.email,
        "password": hashed_password,
        "created_at": datetime.utcnow()
    }

    result = await users.insert_one(user)
    user_id = result.inserted_id

    await finances.insert_one({
        "user_id": str(user_id),
        "user_monthly_expenditure": 1000
    })

    return {
        "message": "Signup successful",
        "user_id": str(user_id)
    }


# -------------------- LOGIN --------------------
@router.post("/login")
async def login(data: LoginRequest):
    users = get_collection("users")

    user = await users.find_one({"email": data.email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not sha256_crypt.verify(data.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )

    return {
        "message": "Login successful",
        "email": user["email"],
        "user_id": str(user["_id"])
    }
