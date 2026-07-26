from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from database import SessionLocal, User

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

@router.post("/request-account")
def request_account(data: AccountRequest, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered or requested.")
    
    # Create user with is_approved = False (pending admin review)
    new_user = User(email=data.email, is_approved=False, is_admin=False)
    db.add(new_user)
    db.commit()
    return {"message": "Account request submitted successfully. Waiting for admin approval."}

@router.post("/register")
def register_user(data: UserRegister, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email request not found.")
    
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Account has not been approved by an administrator yet.")
    
    if user.username:
        raise HTTPException(status_code=400, detail="Account is already fully registered.")

    # Hash the password securely
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