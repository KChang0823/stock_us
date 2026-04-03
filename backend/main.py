"""
美股量化戰情室 — 後端 API (FastAPI)
Phase 1B: 讀取 Google Sheet + DCF 估值引擎
"""
from __future__ import annotations

import sys
import math
import json
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
import numpy as np

# 引入 DCF 模型
sys.path.insert(0, '../.agent/skills/creating-financial-models')
from dcf_model import DCFModel

app = FastAPI(title="美股量化戰情室 API", version="1.0.0")

# 允許前端跨域存取 (之後 React 會需要)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Google Sheets 設定 ────────────────────────────────────────
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
CREDENTIALS_FILE = '../us-stock-492206-c70a26f31b45.json'
SHEET_ID = '1RlIuqWSTXTwnfxapPV8eqThUO4crz9IE4zhC6xH9rUI'


def get_sheet():
    """取得 Google Sheet 連線"""
    credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(credentials)
    return client.open_by_key(SHEET_ID)


def clean_pct(val) -> float:
    """把 '36.31%' 這種字串轉成 0.3631"""
    if isinstance(val, str) and val.endswith('%'):
        return float(val.replace('%', '')) / 100
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


# ── API Endpoints ─────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "message": "量化戰情室大腦已啟動 🧠"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# P0: GET /api/positions — 取得所有持股
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.get("/api/positions")
def get_positions():
    """從 Google Sheet 的 Positions 工作表讀取所有持股"""
    try:
        sheet = get_sheet()
        ws = sheet.worksheet("Positions")
        rows = ws.get_all_records()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取 Positions 失敗: {e}")

    positions = []
    for row in rows:
        ticker = row.get("A: 標的代號 (Ticker)", "")
        if not ticker:
            continue
        positions.append({
            "ticker": ticker,
            "quadrant": row.get("B: 象限分類 (Quadrant)", ""),
            "shares": float(row.get("C: 股數 (Shares)", 0)),
            "avg_cost": float(row.get("D: 平均成本 (Avg Cost)", 0)),
            "current_price": float(row.get("E: 即時股價 (Current Price)", 0)),
            "market_value": float(row.get("F: 總市值 (Market Value)", 0)),
            "allocation_pct": clean_pct(row.get("G: 佔比 (Allocation %)", "0%")),
            "pnl_pct": clean_pct(row.get("H: 未實現損益 (PnL %)", "0%")),
            "internal_pct": clean_pct(row.get("I: 內部佔比(%)", "0%")),
        })

    total_value = sum(p["market_value"] for p in positions)

    return {
        "total_market_value": round(total_value, 2),
        "position_count": len(positions),
        "positions": positions,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# P0: GET /api/dashboard — 取得四象限總覽
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.get("/api/dashboard")
def get_dashboard():
    """從 Google Sheet 的 Dashboard 工作表讀取四象限資料"""
    try:
        sheet = get_sheet()
        ws = sheet.worksheet("Dashboard")
        rows = ws.get_all_records()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取 Dashboard 失敗: {e}")

    quadrants = []
    for row in rows:
        name = row.get("A: 象限 (Quadrant)", "")
        if not name or name == "總計":
            continue
        quadrants.append({
            "name": name,
            "target_pct": clean_pct(row.get("B: 目標佔比", "0%")),
            "tolerance_low": clean_pct(row.get("C: 容忍下限", "0%")),
            "tolerance_high": clean_pct(row.get("D: 容忍上限", "0%")),
            "current_value": float(row.get("E: 當前市值 (Current Value)", 0)),
            "current_pct": clean_pct(row.get("F: 當前佔比 (Current %)", "0%")),
            "alert": row.get("G: 狀態燈號與行動 (Action Alert)", ""),
        })

    return {"quadrants": quadrants}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# P0: GET /api/transactions — 取得交易紀錄
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.get("/api/transactions")
def get_transactions(limit: int = Query(default=50, description="最多回傳幾筆")):
    """從 Google Sheet 的 Transactions 工作表讀取交易紀錄"""
    try:
        sheet = get_sheet()
        ws = sheet.worksheet("Transactions")
        rows = ws.get_all_records()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取 Transactions 失敗: {e}")

    transactions = []
    for row in rows:
        ticker = row.get("代號 (Ticker)", "")
        if not ticker:
            continue
        transactions.append({
            "date": row.get("日期 (Date)", ""),
            "ticker": ticker,
            "action": row.get("動作 (Action)", ""),
            "shares": float(row.get("股數 (Shares)", 0)),
            "price": float(row.get("單價 (Price)", 0)),
            "note": row.get("備註 (Note)", ""),
        })

    # 回傳最新的 N 筆（倒序）
    transactions.reverse()
    return {
        "total_count": len(transactions),
        "transactions": transactions[:limit],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# P0: POST /api/valuation/{ticker} — 自動 DCF 估值
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ValuationParams(BaseModel):
    """使用者可選擇性覆蓋的估值參數"""
    revenue_growth: Optional[list] = None       # 例如 [0.13, 0.12, 0.11, 0.10, 0.09]
    terminal_growth: Optional[float] = None     # 例如 0.03
    risk_free_rate: Optional[float] = None      # 例如 0.043
    market_premium: Optional[float] = None      # 例如 0.055
    margin_of_safety: Optional[float] = 0.85    # 安全邊際折數 (預設 85 折)


@app.post("/api/valuation/{ticker}")
def run_valuation(ticker: str, params: ValuationParams = ValuationParams()):
    """
    對指定標的執行完整的 DCF 估值分析。
    自動從 yfinance 抓取財報，使用 creating-financial-models 技能的 DCF 引擎運算。
    """
    try:
        import yfinance as yf
    except ImportError:
        raise HTTPException(status_code=500, detail="缺少 yfinance 套件，請執行 pip install yfinance")

    ticker = ticker.upper()

    # ── 1. 從 Yahoo Finance 抓取財報 ──
    stock = yf.Ticker(ticker)
    info = stock.info
    income_stmt = stock.financials
    balance_sheet = stock.balance_sheet
    cash_flow_stmt = stock.cashflow

    if income_stmt is None or income_stmt.empty:
        raise HTTPException(status_code=404, detail=f"找不到 {ticker} 的財報數據")

    # 排序（舊→新）
    income_stmt = income_stmt[sorted(income_stmt.columns)]
    balance_sheet = balance_sheet[sorted(balance_sheet.columns)]
    cash_flow_stmt = cash_flow_stmt[sorted(cash_flow_stmt.columns)]

    # ── 2. 萃取歷史數據 ──
    years_raw, revenue, ebitda_list, capex_list, nwc_list = [], [], [], [], []

    for col in income_stmt.columns:
        years_raw.append(col.year)
        rev = income_stmt.loc['Total Revenue', col] / 1e6
        revenue.append(rev)
        try:
            eb = income_stmt.loc['EBITDA', col] / 1e6
        except KeyError:
            try:
                op = income_stmt.loc['Operating Income', col] / 1e6
                da = cash_flow_stmt.loc['Depreciation And Amortization', col] / 1e6
                eb = op + da
            except KeyError:
                eb = rev * 0.30
        ebitda_list.append(eb)

    for col in cash_flow_stmt.columns:
        try:
            cx = abs(cash_flow_stmt.loc['Capital Expenditure', col]) / 1e6
        except KeyError:
            cx = 0
        capex_list.append(cx)

    for col in balance_sheet.columns:
        try:
            ca = balance_sheet.loc['Current Assets', col] / 1e6
            cl = balance_sheet.loc['Current Liabilities', col] / 1e6
            nwc_list.append(ca - cl)
        except KeyError:
            nwc_list.append(0)

    # 過濾 NaN
    valid = [i for i in range(len(years_raw))
             if not any(math.isnan(x) for x in [revenue[i], ebitda_list[i], capex_list[i], nwc_list[i]])]
    years = [years_raw[i] for i in valid]
    revenue = [revenue[i] for i in valid]
    ebitda_list = [ebitda_list[i] for i in valid]
    capex_list = [capex_list[i] for i in valid]
    nwc_list = [nwc_list[i] for i in valid]

    if len(years) < 2:
        raise HTTPException(status_code=400, detail=f"{ticker} 的有效財報數據不足（需要至少 2 年）")

    # ── 3. 計算 WACC 參數 ──
    beta = info.get('beta', 1.0)
    shares_out = info.get('sharesOutstanding', 1) / 1e6
    current_price = info.get('currentPrice', info.get('previousClose', 0))

    latest_bs = balance_sheet.columns[-1]
    try:
        total_debt = balance_sheet.loc['Total Debt', latest_bs] / 1e6
    except KeyError:
        try:
            total_debt = balance_sheet.loc['Long Term Debt', latest_bs] / 1e6
        except KeyError:
            total_debt = 0

    try:
        cash = balance_sheet.loc['Cash And Cash Equivalents', latest_bs] / 1e6
    except KeyError:
        try:
            cash = balance_sheet.loc['Cash Cash Equivalents And Short Term Investments', latest_bs] / 1e6
        except KeyError:
            cash = 0

    market_cap = current_price * shares_out
    d_e = total_debt / market_cap if market_cap > 0 else 0.05
    net_debt = total_debt - cash

    risk_free = params.risk_free_rate or 0.043
    mkt_premium = params.market_premium or 0.055
    cost_of_debt = 0.04
    tax_rate = 0.15

    # ── 4. 設定成長假設 ──
    proj_years = 5
    if params.revenue_growth and len(params.revenue_growth) == proj_years:
        rev_growth = params.revenue_growth
    else:
        # 用歷史 CAGR 推估，然後逐年遞減
        hist_cagr = (revenue[-1] / revenue[0]) ** (1 / (len(revenue) - 1)) - 1
        base_g = min(max(hist_cagr, 0.05), 0.20)  # 限制在 5%~20%
        rev_growth = [round(base_g - 0.01 * i, 3) for i in range(proj_years)]

    terminal_g = params.terminal_growth or 0.03

    hist_margins = [ebitda_list[i] / revenue[i] for i in range(len(revenue))]
    avg_margin = float(np.mean(hist_margins))
    ebitda_margins = [min(avg_margin + 0.005 * i, 0.50) for i in range(proj_years)]

    hist_capex_pct = [capex_list[i] / revenue[i] for i in range(len(revenue))]
    avg_capex = float(np.mean(hist_capex_pct))
    capex_pcts = [avg_capex] * proj_years

    hist_nwc_pct = [abs(nwc_list[i] / revenue[i]) for i in range(len(revenue))]
    avg_nwc = float(np.mean(hist_nwc_pct))
    nwc_pcts = [avg_nwc] * proj_years

    # ── 5. 執行 DCF 模型 ──
    model = DCFModel(f"{info.get('shortName', ticker)} ({ticker})")
    model.set_historical_financials(revenue=revenue, ebitda=ebitda_list, capex=capex_list, nwc=nwc_list, years=years)
    model.set_assumptions(
        projection_years=proj_years,
        revenue_growth=rev_growth,
        ebitda_margin=ebitda_margins,
        tax_rate=tax_rate,
        capex_percent=capex_pcts,
        nwc_percent=nwc_pcts,
        terminal_growth=terminal_g,
    )
    wacc = model.calculate_wacc(
        risk_free_rate=risk_free, beta=beta, market_premium=mkt_premium,
        cost_of_debt=cost_of_debt, debt_to_equity=d_e, tax_rate=tax_rate,
    )
    projections = model.project_cash_flows()
    ev_results = model.calculate_enterprise_value(terminal_method="growth")
    eq_results = model.calculate_equity_value(net_debt=net_debt, cash=0, shares_outstanding=shares_out)

    fair_value = eq_results['value_per_share']
    safety_price = fair_value * (params.margin_of_safety or 0.85)
    upside = (fair_value - current_price) / current_price * 100 if current_price > 0 else 0

    # ── 6. 敏感度分析 ──
    wacc_range = [wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02]
    tg_range = [0.02, 0.025, 0.03, 0.035, 0.04]
    sensitivity = []
    for w in wacc_range:
        row = []
        for tg in tg_range:
            model.wacc_components['wacc'] = w
            model.assumptions['terminal_growth'] = tg
            model.project_cash_flows()
            model.calculate_enterprise_value()
            eq = model.calculate_equity_value(net_debt=net_debt, cash=0, shares_outstanding=shares_out)
            row.append(round(eq['value_per_share'], 2))
        sensitivity.append(row)
    # restore
    model.wacc_components['wacc'] = wacc
    model.assumptions['terminal_growth'] = terminal_g

    # ── 7. 回傳結果 ──
    return {
        "ticker": ticker,
        "company_name": info.get('shortName', ticker),
        "current_price": current_price,
        "fair_value": round(fair_value, 2),
        "safety_price": round(safety_price, 2),
        "upside_pct": round(upside, 1),
        "verdict": "低估 ✅" if upside > 0 else "高估 ⚠️",
        "wacc": round(wacc * 100, 2),
        "beta": beta,
        "assumptions": {
            "revenue_growth": rev_growth,
            "ebitda_margins": [round(m, 4) for m in ebitda_margins],
            "terminal_growth": terminal_g,
            "risk_free_rate": risk_free,
            "market_premium": mkt_premium,
        },
        "projections": {
            "years": projections['year'],
            "revenue_m": [round(r, 0) for r in projections['revenue']],
            "ebitda_m": [round(e, 0) for e in projections['ebitda']],
            "fcf_m": [round(f, 0) for f in projections['fcf']],
        },
        "valuation": {
            "enterprise_value_m": round(ev_results['enterprise_value'], 0),
            "equity_value_m": round(eq_results['equity_value'], 0),
            "terminal_pct": round(ev_results['terminal_percent'], 1),
        },
        "sensitivity": {
            "wacc_range_pct": [round(w * 100, 2) for w in wacc_range],
            "tg_range_pct": [round(t * 100, 1) for t in tg_range],
            "matrix_per_share": sensitivity,
        },
        "historical": {
            "years": years,
            "revenue_m": [round(r, 0) for r in revenue],
            "ebitda_m": [round(e, 0) for e in ebitda_list],
            "ebitda_margin": [round(m, 4) for m in hist_margins],
        },
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# P1: GET /api/price/{ticker} — 快速查詢即時股價
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.get("/api/price/{ticker}")
def get_price(ticker: str):
    """查詢單一標的的即時股價"""
    try:
        import yfinance as yf
    except ImportError:
        raise HTTPException(status_code=500, detail="缺少 yfinance")

    stock = yf.Ticker(ticker.upper())
    info = stock.info
    return {
        "ticker": ticker.upper(),
        "name": info.get("shortName", ""),
        "price": info.get("currentPrice", info.get("previousClose", None)),
        "market_cap_b": round(info.get("marketCap", 0) / 1e9, 2),
        "pe_ratio": info.get("trailingPE"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
    }
