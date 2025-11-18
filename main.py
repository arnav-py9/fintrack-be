from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.endpoints import sample_endpoint
from app.endpoints import users_endpoints

app = FastAPI(
    title="FinTrack API",
    description="Backend API for the FinTrack application",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sample_endpoint.router, prefix="/api", tags=["Sample"])
app.include_router(users_endpoints.router, prefix="/api", tags=["Users"])

@app.get("/")
def root():
    return {"message": "🚀 FinTrack API is running successfully!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
    

