import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests
import yfinance as yf
import pandas as pd
import numpy as np

# Import the authentication router from auth.py
from .auth import router as auth_router
from .database import engine, Base

app = FastAPI(title="InvestmentAI Backend")
# Initialize the SQLite database tables
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect the auth endpoints with the /auth prefix
app.include_router(auth_router, prefix="/auth")

DB_FILE = "database.json"

def load_db():
  if not os.path.exists(DB_FILE):
    return {}
  try:
    with open(DB_FILE, "r") as f:
      return json.load(f)
  except Exception:
    return {}

def save_db(data):
  with open(DB_FILE, "w") as f:
    json.dump(data, f, indent=4)

# Pydantic Models
class TickerItem(BaseModel):
  symbol: str
  shares: float = 0.0
  buy_price: float = 0.0

class StockItem(BaseModel):
  symbol: str
  shares: float = 0.0
  avg_cost: float = 0.0
  target_price: float = 0.0
  notes: str = ""

class CryptoItem(BaseModel):
  symbol: str
  units: float = 0.0
  avg_cost: float = 0.0
  target_price: float = 0.0
  notes: str = ""

class OptionItem(BaseModel):
  symbol: str
  type: str = "Call"
  action: str = "Buy"
  contracts: int = 0
  strike: float = 0.0
  cost: float = 0.0
  premium: float = 0.0
  expiration: str = ""
  target: float = 0.0
  notes: str = ""

class WatchlistItem(BaseModel):
  symbol: str
  target_price: float = 0.0
  notes: str = ""

class PortfolioPayload(BaseModel):
  username: str
  tickers: list[TickerItem] = []

class StocksPayload(BaseModel):
  username: str
  items: list[StockItem] = []

class CryptoPayload(BaseModel):
  username: str
  items: list[CryptoItem] = []

class OptionsPayload(BaseModel):
  username: str
  items: list[OptionItem] = []

class WatchlistPayload(BaseModel):
  username: str
  items: list[WatchlistItem] = []

# Configure requests Session with User-Agent for yfinance
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
})

def calculate_fundamental_scores(ticker_obj):
  """
  Calculates Piotroski F-Score (0-9) and Altman Z-Score for financial health & distress prediction.
  """
  try:
    bs = ticker_obj.balance_sheet
    inc = ticker_obj.financials
    cf = ticker_obj.cashflow
    info = ticker_obj.info

    if bs.empty or inc.empty or cf.empty or len(bs.columns) < 2:
      return {"f_score": "N/A", "z_score": "N/A", "z_zone": "N/A"}

    # --- Altman Z-Score Calculation ---
    total_assets = bs.iloc[:, 0].get("Total Assets", 1)
    total_liabilities = bs.iloc[:, 0].get("Total Liabilities Net Minority Interest", 1)
    if total_liabilities == 0:
      total_liabilities = 1

    working_capital = bs.iloc[:, 0].get("Working Capital", 0)
    retained_earnings = bs.iloc[:, 0].get("Retained Earnings", 0)
    ebit = inc.iloc[:, 0].get("EBIT", 0)
    sales = inc.iloc[:, 0].get("Total Revenue", 0)
    market_cap = info.get("marketCap", total_assets)

    x1 = working_capital / total_assets
    x2 = retained_earnings / total_assets
    x3 = ebit / total_assets
    x4 = market_cap / total_liabilities
    x5 = sales / total_assets

    z_score = (1.2 * x1) + (1.4 * x2) + (3.3 * x3) + (0.6 * x4) + (0.999 * x5)
    z_score_rounded = round(float(z_score), 2)

    if z_score_rounded > 2.99:
      z_zone = "Safe Zone"
    elif 1.81 <= z_score_rounded <= 2.99:
      z_zone = "Grey Zone"
    else:
      z_zone = "Distress Zone"

    # --- Piotroski F-Score Calculation (0-9 Range) ---
    f_score = 0
    cy_net_income = inc.iloc[:, 0].get("Net Income", 0)
    cy_operating_cf = cf.iloc[:, 0].get("Operating Cash Flow", 0)
    cy_assets = bs.iloc[:, 0].get("Total Assets", 1)
    cy_roa = cy_net_income / cy_assets if cy_assets else 0

    cy_long_term_debt = bs.iloc[:, 0].get("Long Term Debt", 0)
    cy_current_assets = bs.iloc[:, 0].get("Current Assets", 0)
    cy_current_liabilities = bs.iloc[:, 0].get("Current Liabilities", 1)
    cy_current_ratio = cy_current_assets / cy_current_liabilities if cy_current_liabilities else 0
    cy_shares = bs.iloc[:, 0].get("Ordinary Shares Number", 1)

    cy_sales = inc.iloc[:, 0].get("Total Revenue", 0)
    cy_gross_margin = (inc.iloc[:, 0].get("Gross Profit", 0) / cy_sales) if cy_sales else 0
    cy_asset_turnover = cy_sales / cy_assets if cy_assets else 0

    py_net_income = inc.iloc[:, 1].get("Net Income", 0)
    py_assets = bs.iloc[:, 1].get("Total Assets", 1)
    py_roa = py_net_income / py_assets if py_assets else 0
    py_long_term_debt = bs.iloc[:, 1].get("Long Term Debt", 0)
    py_current_assets = bs.iloc[:, 1].get("Current Assets", 0)
    py_current_liabilities = bs.iloc[:, 1].get("Current Liabilities", 1)
    py_current_ratio = py_current_assets / py_current_liabilities if py_current_liabilities else 0
    py_shares = bs.iloc[:, 1].get("Ordinary Shares Number", 1)
    py_sales = inc.iloc[:, 1].get("Total Revenue", 1)
    py_gross_margin = (inc.iloc[:, 1].get("Gross Profit", 0) / py_sales) if py_sales else 0
    py_asset_turnover = py_sales / py_assets if py_assets else 0

    if cy_roa > 0: f_score += 1
    if cy_operating_cf > 0: f_score += 1
    if cy_roa > py_roa: f_score += 1
    if cy_operating_cf > cy_net_income: f_score += 1
    if cy_long_term_debt <= py_long_term_debt: f_score += 1
    if cy_current_ratio > py_current_ratio: f_score += 1
    if cy_shares <= py_shares: f_score += 1
    if cy_gross_margin > py_gross_margin: f_score += 1
    if cy_asset_turnover > py_asset_turnover: f_score += 1

    return {
        "f_score": int(f_score),
        "z_score": z_score_rounded,
        "z_zone": z_zone
    }
  except Exception:
    return {"f_score": "N/A", "z_score": "N/A", "z_zone": "N/A"}

# --- NEW TICKERS ---
@app.get("/portfolio/{username}/new-tickers")
def get_new_tickers(username: str):
  db = load_db()
  return {
      "status": "success",
      "tickers": db.get(username, {}).get("new_tickers", []),
  }

@app.post("/portfolio/validate-and-save")
def validate_and_save_new(payload: PortfolioPayload):
  validated = []
  for item in payload.tickers:
    symbol = item.symbol.upper().strip()
    if not symbol:
      continue
    try:
      ticker_obj = yf.Ticker(symbol, session=session)
      hist = ticker_obj.history(period="1d")
      if hist.empty:
        raise HTTPException(
            status_code=400, detail=f"Invalid symbol '{symbol}'."
        )
      validated.append({
          "symbol": symbol,
          "shares": item.shares,
          "buy_price": item.buy_price,
      })
    except HTTPException as he:
      raise he
    except Exception as e:
      raise HTTPException(
          status_code=400, detail=f"Error validating '{symbol}': {str(e)}"
      )

  db = load_db()
  if payload.username not in db:
    db[payload.username] = {}
  db[payload.username]["new_tickers"] = validated
  save_db(db)
  return {"status": "success", "message": "New tickers saved successfully."}

@app.delete("/portfolio/{username}/clear-new-tickers")
def clear_new_tickers(username: str):
  db = load_db()
  if username in db:
    db[username]["new_tickers"] = []
    save_db(db)
  return {"status": "success", "message": "Cleared successfully."}

# --- STOCKS ---
@app.get("/portfolio/{username}/stocks")
def get_stocks(username: str):
  db = load_db()
  return {"status": "success", "items": db.get(username, {}).get("stocks", [])}

@app.post("/portfolio/stocks/save")
def save_stocks(payload: StocksPayload):
  validated = []
  for item in payload.items:
    symbol = item.symbol.upper().strip()
    if not symbol:
      continue
    try:
      ticker_obj = yf.Ticker(symbol, session=session)
      if ticker_obj.history(period="1d").empty:
        raise HTTPException(
            status_code=400, detail=f"Invalid stock symbol '{symbol}'."
        )
      validated.append(item.model_dump())
    except HTTPException as he:
      raise he
    except Exception as e:
      raise HTTPException(
          status_code=400, detail=f"Error validating '{symbol}': {str(e)}"
      )

  db = load_db()
  if payload.username not in db:
    db[payload.username] = {}
  db[payload.username]["stocks"] = validated
  save_db(db)
  return {"status": "success", "message": "Stocks saved successfully."}

@app.delete("/portfolio/{username}/stocks")
def clear_stocks(username: str):
  db = load_db()
  if username in db:
    db[username]["stocks"] = []
    save_db(db)
  return {"status": "success", "message": "Stocks cleared."}

# --- CRYPTO ---
@app.get("/portfolio/{username}/crypto")
def get_crypto(username: str):
  db = load_db()
  return {"status": "success", "items": db.get(username, {}).get("crypto", [])}

@app.post("/portfolio/crypto/save")
def save_crypto(payload: CryptoPayload):
  validated = []
  for item in payload.items:
    symbol = item.symbol.upper().strip()
    if not symbol:
      continue
    query_sym = symbol if "-" in symbol else f"{symbol}-USD"
    try:
      ticker_obj = yf.Ticker(query_sym, session=session)
      if ticker_obj.history(period="1d").empty:
        ticker_obj = yf.Ticker(symbol, session=session)
        if ticker_obj.history(period="1d").empty:
          raise HTTPException(
              status_code=400, detail=f"Invalid crypto symbol '{symbol}'."
          )
      validated.append(item.model_dump())
    except HTTPException as he:
      raise he
    except Exception as e:
      raise HTTPException(
          status_code=400, detail=f"Error validating '{symbol}': {str(e)}"
      )

  db = load_db()
  if payload.username not in db:
    db[payload.username] = {}
  db[payload.username]["crypto"] = validated
  save_db(db)
  return {"status": "success", "message": "Crypto saved successfully."}

@app.delete("/portfolio/{username}/crypto")
def clear_crypto(username: str):
  db = load_db()
  if username in db:
    db[username]["crypto"] = []
    save_db(db)
  return {"status": "success", "message": "Crypto cleared."}

# --- OPTIONS ---
@app.get("/portfolio/{username}/options")
def get_options(username: str):
  db = load_db()
  return {"status": "success", "items": db.get(username, {}).get("options", [])}

@app.post("/portfolio/options/save")
def save_options(payload: OptionsPayload):
  validated = [item.model_dump() for item in payload.items if item.symbol.strip()]
  db = load_db()
  if payload.username not in db:
    db[payload.username] = {}
  db[payload.username]["options"] = validated
  save_db(db)
  return {"status": "success", "message": "Options saved successfully."}

@app.delete("/portfolio/{username}/options")
def clear_options(username: str):
  db = load_db()
  if username in db:
    db[username]["options"] = []
    save_db(db)
  return {"status": "success", "message": "Options cleared."}

# --- WATCHLIST ---
@app.get("/portfolio/{username}/watchlist")
def get_watchlist(username: str):
  db = load_db()
  return {
      "status": "success",
      "items": db.get(username, {}).get("watchlist", []),
  }

@app.post("/portfolio/watchlist/save")
def save_watchlist(payload: WatchlistPayload):
  validated = []
  for item in payload.items:
    symbol = item.symbol.upper().strip()
    if not symbol:
      continue
    try:
      ticker_obj = yf.Ticker(symbol, session=session)
      if ticker_obj.history(period="1d").empty:
        if yf.Ticker(f"{symbol}-USD", session=session).history(period="1d").empty:
          raise HTTPException(
              status_code=400, detail=f"Invalid watchlist symbol '{symbol}'."
          )
      validated.append(item.model_dump())
    except HTTPException as he:
      raise he
    except Exception as e:
      raise HTTPException(
          status_code=400, detail=f"Error validating '{symbol}': {str(e)}"
      )

  db = load_db()
  if payload.username not in db:
    db[payload.username] = {}
  db[payload.username]["watchlist"] = validated
  save_db(db)
  return {"status": "success", "message": "Watchlist saved successfully."}

@app.delete("/portfolio/{username}/watchlist")
def clear_watchlist(username: str):
  db = load_db()
  if username in db:
    db[username]["watchlist"] = []
    save_db(db)
  return {"status": "success", "message": "Watchlist cleared."}

# --- VALUATION TAB API ---
@app.get("/portfolio/{username}/valuation")
def get_valuation(username: str):
  db = load_db()
  user_data = db.get(username, {})
  stocks = user_data.get("stocks", [])
  crypto = user_data.get("crypto", [])
  watchlist = user_data.get("watchlist", [])

  holdings = []
  total_value = 0.0
  total_cost_basis = 0.0

  for s in stocks:
    sym = s.get("symbol")
    shares = float(s.get("shares", 0))
    avg_cost = float(s.get("avg_cost", 0))
    if not sym or shares <= 0:
      continue
    try:
      t = yf.Ticker(sym, session=session)
      hist = t.history(period="2d")
      if hist.empty:
        current_price = avg_cost
        prev_close = avg_cost
      else:
        current_price = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price

      cost_basis = shares * avg_cost
      curr_val = shares * current_price
      total_pnl = curr_val - cost_basis
      total_return_pct = (total_pnl / cost_basis * 100) if cost_basis > 0 else 0
      day_pnl = shares * (current_price - prev_close)

      total_value += curr_val
      total_cost_basis += cost_basis

      holdings.append({
          "ticker": sym,
          "shares": shares,
          "avg_cost": avg_cost,
          "current_price": current_price,
          "day_pnl": day_pnl,
          "total_pnl": total_pnl,
          "total_return_pct": total_return_pct,
          "current_total_value": curr_val,
      })
    except Exception:
      pass

  for c in crypto:
    sym = c.get("symbol")
    units = float(c.get("units", 0))
    avg_cost = float(c.get("avg_cost", 0))
    if not sym or units <= 0:
      continue

    query_sym = sym if "-" in sym else f"{sym}-USD"
    try:
      t = yf.Ticker(query_sym, session=session)
      hist = t.history(period="2d")
      if hist.empty:
        t = yf.Ticker(sym, session=session)
        hist = t.history(period="2d")

      if hist.empty:
        current_price = avg_cost
        prev_close = avg_cost
      else:
        current_price = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price

      cost_basis = units * avg_cost
      curr_val = units * current_price
      total_pnl = curr_val - cost_basis
      total_return_pct = (total_pnl / cost_basis * 100) if cost_basis > 0 else 0
      day_pnl = units * (current_price - prev_close)

      total_value += curr_val
      total_cost_basis += cost_basis

      holdings.append({
          "ticker": sym,
          "shares": units,
          "avg_cost": avg_cost,
          "current_price": current_price,
          "day_pnl": day_pnl,
          "total_pnl": total_pnl,
          "total_return_pct": total_return_pct,
          "current_total_value": curr_val,
      })
    except Exception:
      pass

  unrealized_pnl = total_value - total_cost_basis
  return_pct = (unrealized_pnl / total_cost_basis * 100) if total_cost_basis > 0 else 0

  summary = {
      "total_value": total_value,
      "cost_basis": total_cost_basis,
      "unrealized_pnl": unrealized_pnl,
      "return_pct": return_pct,
  }

  watchlist_resolved = []
  for w in watchlist:
    sym = w.get("symbol")
    target = float(w.get("target_price", 0))
    notes = w.get("notes", "")
    if not sym:
      continue

    curr_price = 0.0
    try:
      t = yf.Ticker(sym, session=session)
      hist = t.history(period="1d")
      if hist.empty:
        t = yf.Ticker(f"{sym}-USD", session=session)
        hist = t.history(period="1d")
      if not hist.empty:
        curr_price = float(hist["Close"].iloc[-1])
    except Exception:
      pass

    watchlist_resolved.append({
        "symbol": sym,
        "target_price": target,
        "current_price": curr_price,
        "notes": notes,
    })

  return {
      "status": "success",
      "summary": summary,
      "holdings": holdings,
      "watchlist": watchlist_resolved,
  }

@app.get("/")
def read_root():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    index_path = os.path.join(base_dir, "frontend", "index.html")
    return FileResponse(index_path)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_dir = os.path.join(base_dir, "frontend")
app.mount("/", StaticFiles(directory=frontend_dir), name="frontend")

if __name__ == "__main__":
  import uvicorn
  uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)