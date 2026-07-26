from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
import auth

# Initialize our InvestmentAI app
app = FastAPI(title="InvestmentAI API", version="1.0.0")

# Allow frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database tables on startup
@app.on_event("startup")
on_startup():
    init_db()

# Include authentication routes
app.include_router(auth.router)

@app.get("/")
def read_root():
    return {"status": "online", "message": "Welcome to InvestmentAI Backend!"}