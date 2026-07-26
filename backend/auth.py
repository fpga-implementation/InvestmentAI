import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from database import SessionLocal, User

# Load environment variables securely from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@investmentai.com")
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "default_secret")

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Password hashing setup using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Request data models
class AccountRequest(BaseModel):
    email: str

class UserRegister(BaseModel):
    email: str
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class AdminApproval(BaseModel):
    email_to_approve: str
    admin_secret: str

@router.post("/request-account")
def request_account(data: AccountRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered or requested.")
    
    new_user = User(email=data.email, is_approved=False, is_admin=False)
    db.add(new_user)
    db.commit()
    return {"message": f"Account request submitted. Notification sent to administrator ({ADMIN_EMAIL})."}

@router.post("/admin/approve")
def approve_user(data: AdminApproval, db: Session = Depends(get_db)):
    # Verify local admin secret key for security
    if data.admin_secret != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Invalid administrator secret key.")
    
    user = db.query(User).filter(User.email == data.email_to_approve).first()
    if not user:
        raise HTTPException(status_code=404, detail="User email request not found.")
    
    user.is_approved = True
    db.commit()
    return {"message": f"User {user.email} has been approved successfully! They can now register their username and password."}

@router.post("/register")
def register_user(data: UserRegister, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email request not found.")
    
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Account has not been approved by an administrator yet.")
    
    if user.username:
        raise HTTPException(status_code=400, detail="Account is already fully registered.")

    hashed_password = pwd_context.hash(data.password)
    user.username = data.username
    user.hashed_password = hashed_password
    db.commit()
    
    return {"message": "Account created successfully! You can now log in."}

@router.post("/login")
def login_user(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not user.hashed_password:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    
    if not pwd_context.verify(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Account pending approval.")

    return {"status": "success", "message": f"Welcome back, {user.username}!"}