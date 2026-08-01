import os
import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Import database session and User model
from .database import SessionLocal, User

# Load environment variables
load_dotenv()
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "my_super_secret_admin_key")

router = APIRouter(tags=["Auth"])

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- PYDANTIC MODELS (Must inherit from BaseModel) ---
class AccountRequest(BaseModel):
    email: str

class AdminApproveRequest(BaseModel):
    email_to_approve: str
    admin_secret: str

class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str


# --- ROUTES ---

@router.post("/request-account")
def request_account(data: AccountRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered or requested.")
    
    new_user = User(email=data.email, is_approved=False, is_admin=False)
    db.add(new_user)
    db.commit()
    return {"message": "Account request submitted successfully. Pending administrator review."}

@router.get("/admin/users")
def list_users(admin_secret: str, db: Session = Depends(get_db)):
    if admin_secret != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Invalid administrator secret key.")
    
    users = db.query(User).all()
    return [
        {
            "id": u.id, 
            "email": u.email, 
            "username": u.username, 
            "is_approved": u.is_approved
        } 
        for u in users
    ]

@router.post("/admin/approve")
def approve_account(data: AdminApproveRequest, db: Session = Depends(get_db)):
    if data.admin_secret != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Invalid administrator secret key.")
    
    user = db.query(User).filter(User.email == data.email_to_approve).first()
    if not user:
        raise HTTPException(status_code=404, detail="User request not found.")
    
    user.is_approved = True
    db.commit()
    return {"message": f"Account for {data.email_to_approve} has been approved."}

@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    password_bytes = data.password.encode("utf-8")
    if len(password_bytes) > 72:
        raise HTTPException(status_code=400, detail="Password is too long. Please shorten it.")
        
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Email not found or not requested.")
    if not user.is_approved:
        raise HTTPException(status_code=400, detail="Account pending admin approval.")
    if user.username:
        raise HTTPException(status_code=400, detail="Account already registered.")
        
    # Generate salt and hash natively with bcrypt
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(password_bytes, salt).decode("utf-8")
    
    user.username = data.username
    user.hashed_password = hashed_pw
    db.commit()
    return {"message": "Registration successful."}

@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    password_bytes = data.password.encode("utf-8")
    if len(password_bytes) > 72:
        raise HTTPException(status_code=400, detail="Invalid username or password.")

    user = db.query(User).filter(User.username == data.username).first()
    if not user or not user.hashed_password:
        raise HTTPException(status_code=400, detail="Invalid username or password.")
    
    # Verify natively with bcrypt
    if not bcrypt.checkpw(password_bytes, user.hashed_password.encode("utf-8")):
        raise HTTPException(status_code=400, detail="Invalid username or password.")
        
    return {"message": "Login successful."}