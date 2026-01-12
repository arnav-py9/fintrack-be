from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.endpoints import sample_endpoint
from app.endpoints import auth_endpoint
from app.endpoints import users_endpoint
from app.endpoints import users_finances_endpoint

app = FastAPI(
    title="FinTrack API",
    description="Backend API for the FinTrack application",
    version="1.0.0"
)

# -------------------- CORS --------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
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

# -------------------- ENTRY POINT --------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
