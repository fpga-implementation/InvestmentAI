from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List
import yfinance as yf
from database import SessionLocal, User, UserTicker

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Data models for incoming requests
class TickerEntry(BaseModel):
    symbol: str
    shares: float
    buy_price: float

class SaveTickersRequest(BaseModel):
    username: str
    tickers: List[TickerEntry]

@router.post("/validate-and-save")
def validate_and_save(data: SaveTickersRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    invalid_symbols = []
    valid_data = []

    # 1. Validate each ticker using yfinance
    for item in data.tickers:
        sym = item.symbol.upper().strip()
        if not sym:
            continue
        
        # We use a quick 1-day history fetch to verify if the symbol is real
        ticker = yf.Ticker(sym)
        hist = ticker.history(period="1d")
        
        if hist.empty:
            invalid_symbols.append(sym)
        else:
            valid_data.append({"symbol": sym, "shares": item.shares, "buy_price": item.buy_price})

    # 2. If any symbols are invalid, reject the whole batch and notify the user
    if invalid_symbols:
        return {
            "status": "error", 
            "invalid_symbols": invalid_symbols, 
            "message": f"Validation failed. Incorrect symbols: {', '.join(invalid_symbols)}"
        }

    # 3. If all are valid, clear the old "new" tickers for this user and save the new batch
    db.query(UserTicker).filter(UserTicker.user_id == user.id, UserTicker.section == "new").delete()
    
    for item in valid_data:
        new_ticker = UserTicker(
            user_id=user.id,
            symbol=item["symbol"],
            shares=item["shares"],
            buy_price=item["buy_price"],
            section="new"
        )
        db.add(new_ticker)
        
    db.commit()
    return {"status": "success", "message": "Tickers validated and saved successfully!"}

@router.get("/{username}/new-tickers")
def get_new_tickers(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    # Retrieve persistent data so it survives page refreshes
    tickers = db.query(UserTicker).filter(UserTicker.user_id == user.id, UserTicker.section == "new").all()
    return {"status": "success", "tickers": [{"symbol": t.symbol, "shares": t.shares, "buy_price": t.buy_price} for t in tickers]}

@router.delete("/{username}/clear-new-tickers")
def clear_new_tickers(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    # Wipe only the "new" section for this specific user
    db.query(UserTicker).filter(UserTicker.user_id == user.id, UserTicker.section == "new").delete()
    db.commit()
    return {"status": "success", "message": "New Tickers data cleared."}