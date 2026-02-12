import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.endpoints import sample_endpoint
from app.endpoints import auth_endpoint
from app.endpoints import users_endpoint
from app.endpoints import users_finances_endpoint
from app.endpoints import users_transactions_endpoint
from app.endpoints import users_business_profit_endpoint
from app.endpoints import founders_transactions_endpoint

load_dotenv()


app = FastAPI(
    title="FinTrack API",
    description="Backend API for the FinTrack application",
    version="1.0.0",
    redirect_slashes=False
)

# -------------------- CORS --------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- ROOT --------------------
@app.get("/")
def root():
    return {"message": "🚀 FinTrack API is running successfully!"}

# -------------------- ROUTERS --------------------
app.include_router(sample_endpoint.router, prefix="/api", tags=["Sample"])
app.include_router(auth_endpoint.router, prefix="/api/auth", tags=["Auth"])
app.include_router(users_endpoint.router, prefix="/api/users", tags=["Users"])
app.include_router(
    users_finances_endpoint.router,
    prefix="/api/users-finances",
    tags=["Users Finances"]
)
app.include_router(
    users_transactions_endpoint.router,
    prefix="/api/users-transactions",
    tags=["Users Transactions"]
)

app.include_router(
    users_business_profit_endpoint.router,
    prefix="/api/users-business-profit",
    tags=["Business Profit"]
)

app.include_router(
    founders_transactions_endpoint.router,
    prefix="/api/founders-transactions",
    tags=["Founders Transactions"]
)

# -------------------- ENTRY POINT --------------------
if __name__ == "__main__":
    import uvicorn

    # Read from environment variables
    ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))

    # Enable reload only in local environment
    reload = ENVIRONMENT == "local"

    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=reload
    )
