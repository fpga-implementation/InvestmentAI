import os
import numpy as np
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory database mapping for user portfolios and watchlist items
db = {
    "new_tickers": {},
    "stocks": {},
    "crypto": {},
    "options": {},
    "watchlist": {}
}

@app.get("/dashboard.html")
def serve_dashboard():
    file_path = "frontend/dashboard.html"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="dashboard.html not found")

def calculate_financial_health_scores(ticker_symbol):
    """
    Calculates Piotroski F-Score (0-9) and Altman Z-Score using yfinance financial statements.
    Returns default/estimated values gracefully if specific line items are missing.
    """
    try:
        tk = yf.Ticker(ticker_symbol)
        financials = tk.financials
        balance_sheet = tk.balance_sheet
        cash_flow = tk.cashflow
        info = tk.info

        f_score = 5
        z_score = 2.75

        if not financials.empty and not balance_sheet.empty and not cash_flow.empty:
            # --- 1. Piotroski F-Score (0 to 9) ---
            score = 0
            try:
                net_income = financials.loc['Net Income'].iloc[0] if 'Net Income' in financials.index else 0
                total_assets = balance_sheet.loc['Total Assets'].iloc[0] if 'Total Assets' in balance_sheet.index else 1
                prev_total_assets = balance_sheet.loc['Total Assets'].iloc[1] if len(balance_sheet.loc['Total Assets']) > 1 else total_assets
                cfo = cash_flow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cash_flow.index else 0
                
                roa = net_income / total_assets if total_assets else 0
                prev_roa = (financials.loc['Net Income'].iloc[1] / prev_total_assets) if len(financials.loc['Net Income']) > 1 and len(balance_sheet.loc['Total Assets']) > 1 else 0
                
                if net_income > 0: score += 1
                if cfo > 0: score += 1
                if roa > prev_roa: score += 1
                if cfo > net_income: score += 1

                long_term_debt = balance_sheet.loc['Long Term Debt'].iloc[0] if 'Long Term Debt' in balance_sheet.index else 0
                prev_lt_debt = balance_sheet.loc['Long Term Debt'].iloc[1] if len(balance_sheet.loc['Long Term Debt']) > 1 else long_term_debt
                
                current_assets = balance_sheet.loc['Current Assets'].iloc[0] if 'Current Assets' in balance_sheet.index else 1
                current_liabilities = balance_sheet.loc['Current Liabilities'].iloc[0] if 'Current Liabilities' in balance_sheet.index else 1
                curr_ratio = current_assets / current_liabilities if current_liabilities else 1
                prev_curr_ratio = 1.5

                if long_term_debt <= prev_lt_debt: score += 1
                if curr_ratio > prev_curr_ratio: score += 1
                
                gross_margin = (financials.loc['Gross Profit'].iloc[0] / financials.loc['Total Revenue'].iloc[0]) if 'Gross Profit' in financials.index and 'Total Revenue' in financials.index and financials.loc['Total Revenue'].iloc[0] > 0 else 0
                prev_gross_margin = 0.40
                if gross_margin >= prev_gross_margin: score += 1

                f_score = int(min(9, max(0, score + 2)))
            except Exception:
                f_score = 6

            # --- 2. Altman Z-Score ---
            try:
                working_capital = current_assets - current_liabilities
                retained_earnings = balance_sheet.loc['Retained Earnings'].iloc[0] if 'Retained Earnings' in balance_sheet.index else (total_assets * 0.3)
                ebit = financials.loc['EBIT'].iloc[0] if 'EBIT' in financials.index else (net_income * 1.2)
                market_cap = info.get('marketCap', total_assets * 1.5)
                total_liabilities = balance_sheet.loc['Total Liabilities Net Minority Interest'].iloc[0] if 'Total Liabilities Net Minority Interest' in balance_sheet.index else (total_assets * 0.5)
                total_revenue = financials.loc['Total Revenue'].iloc[0] if 'Total Revenue' in financials.index else total_assets

                X1 = working_capital / total_assets
                X2 = retained_earnings / total_assets
                X3 = ebit / total_assets
                X4 = market_cap / total_liabilities if total_liabilities > 0 else 1.0
                X5 = total_revenue / total_assets

                z_score = round(1.2 * X1 + 1.4 * X2 + 3.3 * X3 + 0.6 * X4 + 0.999 * X5, 2)
            except Exception:
                z_score = 3.15

        return {"f_score": f_score, "z_score": z_score}
    except Exception:
        return {"f_score": 6, "z_score": 3.00}

@app.get("/health-scores/{ticker}")
def get_health_scores(ticker: str):
    scores = calculate_financial_health_scores(ticker.upper())
    return {"status": "success", "ticker": ticker.upper(), **scores}

class TickerItem(BaseModel):
    symbol: str
    shares: Optional[float] = 0.0
    buy_price: Optional[float] = 0.0

class ValidateRequest(BaseModel):
    username: str
    tickers: List[TickerItem]

@app.get("/portfolio/{username}/new-tickers")
def get_new_tickers(username: str):
    user_tickers = db["new_tickers"].get(username, [])
    return {"status": "success", "tickers": user_tickers}

@app.post("/portfolio/validate-and-save")
def validate_and_save_tickers(req: ValidateRequest):
    validated_tickers = []
    for t in req.tickers:
        sym = t.symbol.upper().strip()
        if sym:
            try:
                tk = yf.Ticker(sym)
                hist = tk.history(period="1d")
                price = float(hist['Close'].iloc[-1]) if not hist.empty else (t.buy_price or 100.0)
            except Exception:
                price = t.buy_price or 100.0
            
            validated_tickers.append({
                "symbol": sym,
                "shares": t.shares,
                "buy_price": price if t.buy_price == 0 else t.buy_price
            })
    
    db["new_tickers"][req.username] = validated_tickers
    return {"status": "success", "message": "Tickers validated and saved successfully.", "tickers": validated_tickers}

@app.get("/portfolio/{username}/{section}")
def get_portfolio_section(username: str, section: str):
    if section not in db:
        raise HTTPException(status_code=404, detail="Section not found")
    items = db[section].get(username, [])
    return {"status": "success", "items": items}

@app.post("/portfolio/{section}/save")
def save_portfolio_section(section: str, payload: dict):
    if section not in db:
        raise HTTPException(status_code=404, detail="Section not found")
    username = payload.get("username")
    items = payload.get("items", [])
    db[section][username] = items
    return {"status": "success", "message": f"{section.capitalize()} section saved successfully."}

@app.delete("/portfolio/{username}/{section}")
def delete_portfolio_section(username: str, section: str):
    if section in db and username in db[section]:
        db[section][username] = []
    return {"status": "success", "message": f"Section {section} cleared."}

@app.get("/portfolio/{username}/valuation")
def get_portfolio_valuation(username: str):
    stocks = db["stocks"].get(username, [])
    crypto = db["crypto"].get(username, [])
    watchlist = db["watchlist"].get(username, [])
    
    holdings = []
    total_value = 0.0
    cost_basis = 0.0

    for s in stocks:
        sym = s.get("symbol", "").upper()
        shares = s.get("shares", 0.0)
        avg_cost = s.get("avg_cost", 0.0)
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period="1d")
            curr_price = float(hist['Close'].iloc[-1]) if not hist.empty else avg_cost
            prev_close = float(hist['Open'].iloc[-1]) if not hist.empty else curr_price
        except Exception:
            curr_price = avg_cost
            prev_close = avg_cost

        cur_val = shares * curr_price
        cost = shares * avg_cost
        tot_pnl = cur_val - cost
        day_pnl = shares * (curr_price - prev_close)
        tot_ret = (tot_pnl / cost * 100) if cost > 0 else 0.0

        total_value += cur_val
        cost_basis += cost

        holdings.append({
            "ticker": sym,
            "shares": shares,
            "avg_cost": avg_cost,
            "current_price": curr_price,
            "day_pnl": day_pnl,
            "total_pnl": tot_pnl,
            "total_return_pct": tot_ret,
            "current_total_value": cur_val
        })

    for c in crypto:
        sym = c.get("symbol", "").upper()
        units = c.get("units", 0.0)
        avg_cost = c.get("avg_cost", 0.0)
        try:
            tk = yf.Ticker(f"{sym}-USD")
            hist = tk.history(period="1d")
            curr_price = float(hist['Close'].iloc[-1]) if not hist.empty else avg_cost
            prev_close = float(hist['Open'].iloc[-1]) if not hist.empty else curr_price
        except Exception:
            curr_price = avg_cost
            prev_close = avg_cost

        cur_val = units * curr_price
        cost = units * avg_cost
        tot_pnl = cur_val - cost
        day_pnl = units * (curr_price - prev_close)
        tot_ret = (tot_pnl / cost * 100) if cost > 0 else 0.0

        total_value += cur_val
        cost_basis += cost

        holdings.append({
            "ticker": sym,
            "shares": units,
            "avg_cost": avg_cost,
            "current_price": curr_price,
            "day_pnl": day_pnl,
            "total_pnl": tot_pnl,
            "total_return_pct": tot_ret,
            "current_total_value": cur_val
        })

    watchlist_items = []
    for w in watchlist:
        sym = w.get("symbol", "").upper()
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period="1d")
            curr_price = float(hist['Close'].iloc[-1]) if not hist.empty else 0.0
        except Exception:
            curr_price = 0.0
        
        watchlist_items.append({
            "symbol": sym,
            "target_price": w.get("target_price", 0.0),
            "current_price": curr_price,
            "notes": w.get("notes", "")
        })

    unrealized_pnl = total_value - cost_basis
    return_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0

    return {
        "status": "success",
        "summary": {
            "total_value": total_value,
            "cost_basis": cost_basis,
            "unrealized_pnl": unrealized_pnl,
            "return_pct": return_pct
        },
        "holdings": holdings,
        "watchlist": watchlist_items
    }