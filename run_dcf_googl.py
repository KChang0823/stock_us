"""
GOOGL DCF 估值分析腳本
使用 creating-financial-models 技能的 DCF 引擎，搭配 yfinance 自動抓取財報數據。
"""
import sys
import json
sys.path.insert(0, '.agent/skills/creating-financial-models')

import numpy as np
import yfinance as yf
from dcf_model import DCFModel

TICKER = "GOOGL"
PROJECTION_YEARS = 5

# ── 1. 抓取 GOOGL 真實財務數據 ──────────────────────────────────
print(f"📡 正在從 Yahoo Finance 抓取 {TICKER} 財務數據...")
stock = yf.Ticker(TICKER)

# 取得財報 (年度)
income_stmt = stock.financials          # 損益表
balance_sheet = stock.balance_sheet      # 資產負債表
cash_flow = stock.cashflow              # 現金流量表
info = stock.info                        # 概要資訊

# 倒序排列，讓最舊的年份在前面
income_stmt = income_stmt[sorted(income_stmt.columns)]
balance_sheet = balance_sheet[sorted(balance_sheet.columns)]
cash_flow = cash_flow[sorted(cash_flow.columns)]

# 提取歷史數據（單位：百萬美元）
years = [col.year for col in income_stmt.columns]

revenue = []
ebitda = []
capex = []
nwc = []

for col in income_stmt.columns:
    rev = income_stmt.loc['Total Revenue', col] / 1e6
    revenue.append(rev)

    # EBITDA: 嘗試從報表取得，若無則用 Operating Income + D&A 估算
    try:
        eb = income_stmt.loc['EBITDA', col] / 1e6
    except KeyError:
        try:
            op_income = income_stmt.loc['Operating Income', col] / 1e6
            da = cash_flow.loc['Depreciation And Amortization', col] / 1e6
            eb = op_income + da
        except KeyError:
            eb = rev * 0.35  # fallback
    ebitda.append(eb)

for col in cash_flow.columns:
    try:
        cx = abs(cash_flow.loc['Capital Expenditure', col]) / 1e6
    except KeyError:
        cx = revenue[cash_flow.columns.tolist().index(col)] * 0.12
    capex.append(cx)

for col in balance_sheet.columns:
    try:
        ca = balance_sheet.loc['Current Assets', col] / 1e6
        cl = balance_sheet.loc['Current Liabilities', col] / 1e6
        nwc.append(ca - cl)
    except KeyError:
        nwc.append(revenue[balance_sheet.columns.tolist().index(col)] * 0.10)

# ── 過濾掉含 NaN 的年份 ──────────────────────────────────────
import math
valid_indices = []
for i in range(len(years)):
    if (not math.isnan(revenue[i]) and not math.isnan(ebitda[i])
            and not math.isnan(capex[i]) and not math.isnan(nwc[i])):
        valid_indices.append(i)

years = [years[i] for i in valid_indices]
revenue = [revenue[i] for i in valid_indices]
ebitda = [ebitda[i] for i in valid_indices]
capex = [capex[i] for i in valid_indices]
nwc = [nwc[i] for i in valid_indices]

print(f"✅ 成功取得 {len(years)} 年有效數據: {years}")
print(f"   營收 (M): {[f'{r:,.0f}' for r in revenue]}")
print(f"   EBITDA (M): {[f'{e:,.0f}' for e in ebitda]}")
print(f"   CAPEX (M): {[f'{c:,.0f}' for c in capex]}")

# ── 2. 取得 WACC 參數 ──────────────────────────────────────────
beta = info.get('beta', 1.05)
shares_outstanding = info.get('sharesOutstanding', 12_200_000_000) / 1e6  # 轉為百萬股
current_price = info.get('currentPrice', info.get('previousClose', 160))

# 取得資產負債表數據
latest_bs = balance_sheet.columns[-1]
try:
    total_debt = balance_sheet.loc['Total Debt', latest_bs] / 1e6
except KeyError:
    try:
        total_debt = balance_sheet.loc['Long Term Debt', latest_bs] / 1e6
    except KeyError:
        total_debt = 30000  # 預設值

try:
    cash = balance_sheet.loc['Cash And Cash Equivalents', latest_bs] / 1e6
except KeyError:
    try:
        cash = balance_sheet.loc['Cash Cash Equivalents And Short Term Investments', latest_bs] / 1e6
    except KeyError:
        cash = 90000  # 預設值

market_cap = current_price * shares_outstanding  # 百萬美元
debt_to_equity = total_debt / market_cap if market_cap > 0 else 0.05
net_debt = total_debt - cash

# WACC 輸入參數
risk_free_rate = 0.043   # 美國10年期公債殖利率（約 4.3%，近期水準）
market_premium = 0.055   # 股權風險溢酬
cost_of_debt = 0.035     # Google 信用評級極高，借貸成本低
tax_rate = 0.135         # Google 有效稅率約 13-14%

print(f"\n📊 WACC 參數:")
print(f"   Beta: {beta:.2f}")
print(f"   無風險利率: {risk_free_rate:.1%}")
print(f"   市場風險溢酬: {market_premium:.1%}")
print(f"   舉債成本: {cost_of_debt:.1%}")
print(f"   D/E Ratio: {debt_to_equity:.4f}")
print(f"   有效稅率: {tax_rate:.1%}")
print(f"   總負債 (M): ${total_debt:,.0f}")
print(f"   現金 (M): ${cash:,.0f}")
print(f"   淨負債 (M): ${net_debt:,.0f}")
print(f"   流通股數 (M): {shares_outstanding:,.0f}")
print(f"   當前股價: ${current_price:.2f}")

# ── 3. 設定成長假設（Base Case / 市場共識） ───────────────────
# Google 2024 營收約 $350B, 市場共識預估未來 5 年成長率
revenue_growth = [0.13, 0.12, 0.11, 0.10, 0.09]  # 遞減成長（AI 紅利逐漸正常化）

# EBITDA margin 基於歷史推估
hist_margins = [ebitda[i] / revenue[i] for i in range(len(revenue))]
avg_margin = np.mean(hist_margins)
# 假設利潤率略微提升（AI 效率提升 & 雲端業務成長）
ebitda_margins = [avg_margin + 0.01 * i for i in range(PROJECTION_YEARS)]
ebitda_margins = [min(m, 0.45) for m in ebitda_margins]  # 上限 45%

# CapEx 佔營收比 (Google AI 基建支出維持高位)
hist_capex_pct = [capex[i] / revenue[i] for i in range(len(revenue))]
avg_capex_pct = np.mean(hist_capex_pct)
capex_pcts = [avg_capex_pct] * PROJECTION_YEARS

# NWC 佔營收比
hist_nwc_pct = [nwc[i] / revenue[i] for i in range(len(revenue))]
avg_nwc_pct = abs(np.mean(hist_nwc_pct))
nwc_pcts = [avg_nwc_pct] * PROJECTION_YEARS

terminal_growth = 0.03  # 永續成長率 3%

# ── 4. 建立 DCF 模型 ──────────────────────────────────────────
print(f"\n🔧 建立 DCF 模型...")
model = DCFModel(f"Alphabet Inc. ({TICKER})")

model.set_historical_financials(
    revenue=revenue,
    ebitda=ebitda,
    capex=capex,
    nwc=nwc,
    years=years,
)

model.set_assumptions(
    projection_years=PROJECTION_YEARS,
    revenue_growth=revenue_growth,
    ebitda_margin=ebitda_margins,
    tax_rate=tax_rate,
    capex_percent=capex_pcts,
    nwc_percent=nwc_pcts,
    terminal_growth=terminal_growth,
)

wacc = model.calculate_wacc(
    risk_free_rate=risk_free_rate,
    beta=beta,
    market_premium=market_premium,
    cost_of_debt=cost_of_debt,
    debt_to_equity=debt_to_equity,
    tax_rate=tax_rate,
)

print(f"   WACC: {wacc:.2%}")

# 推算現金流
projections = model.project_cash_flows()

# 計算企業價值
ev_results = model.calculate_enterprise_value(terminal_method="growth")

# 計算股東權益價值
equity_results = model.calculate_equity_value(
    net_debt=net_debt,
    cash=0,  # 已經在 net_debt 中扣除
    shares_outstanding=shares_outstanding,
)

print(f"\n{'='*60}")
print(model.generate_summary())

# ── 5. 敏感度分析 (WACC vs Terminal Growth) ───────────────────
print(f"\n📊 敏感度分析矩陣 (每股內在價值):")
print(f"   (行 = WACC, 列 = 永續成長率)")

wacc_range = [wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02]
tg_range = [0.02, 0.025, 0.03, 0.035, 0.04]

sensitivity_matrix = []
for w in wacc_range:
    row = []
    for tg in tg_range:
        # 暫時修改 WACC 和 terminal growth
        model.wacc_components['wacc'] = w
        model.assumptions['terminal_growth'] = tg
        model.project_cash_flows()
        ev = model.calculate_enterprise_value()
        eq = model.calculate_equity_value(
            net_debt=net_debt, cash=0, shares_outstanding=shares_outstanding
        )
        row.append(eq['value_per_share'])
    sensitivity_matrix.append(row)

# 恢復原始值
model.wacc_components['wacc'] = wacc
model.assumptions['terminal_growth'] = terminal_growth

# ── 6. 情境分析 ───────────────────────────────────────────────
scenarios = {}
scenario_configs = {
    "🐻 Bear (悲觀)": {"growth": [0.08, 0.07, 0.06, 0.05, 0.04], "margin_adj": -0.03, "tg": 0.02},
    "📊 Base (基準)": {"growth": revenue_growth, "margin_adj": 0.0, "tg": 0.03},
    "🚀 Bull (樂觀)": {"growth": [0.16, 0.15, 0.14, 0.13, 0.12], "margin_adj": 0.02, "tg": 0.035},
}

for name, cfg in scenario_configs.items():
    model.wacc_components['wacc'] = wacc
    model.assumptions['revenue_growth'] = cfg['growth']
    model.assumptions['ebitda_margin'] = [m + cfg['margin_adj'] for m in ebitda_margins]
    model.assumptions['terminal_growth'] = cfg['tg']
    model.project_cash_flows()
    ev = model.calculate_enterprise_value()
    eq = model.calculate_equity_value(
        net_debt=net_debt, cash=0, shares_outstanding=shares_outstanding
    )
    scenarios[name] = {
        'value_per_share': eq['value_per_share'],
        'enterprise_value': ev['enterprise_value'],
        'growth': cfg['growth'],
        'tg': cfg['tg'],
    }

# 恢復
model.wacc_components['wacc'] = wacc
model.assumptions['revenue_growth'] = revenue_growth
model.assumptions['ebitda_margin'] = ebitda_margins
model.assumptions['terminal_growth'] = terminal_growth

# ── 7. 輸出 JSON 供 Markdown 報告使用 ─────────────────────────
output = {
    "ticker": TICKER,
    "company_name": "Alphabet Inc.",
    "current_price": current_price,
    "wacc": wacc,
    "beta": beta,
    "risk_free_rate": risk_free_rate,
    "market_premium": market_premium,
    "cost_of_debt": cost_of_debt,
    "debt_to_equity": debt_to_equity,
    "tax_rate": tax_rate,
    "terminal_growth": terminal_growth,
    "total_debt_m": total_debt,
    "cash_m": cash,
    "net_debt_m": net_debt,
    "shares_outstanding_m": shares_outstanding,
    "historical": {
        "years": years,
        "revenue_m": revenue,
        "ebitda_m": ebitda,
        "capex_m": capex,
        "ebitda_margin": hist_margins,
        "capex_pct": hist_capex_pct,
    },
    "assumptions": {
        "revenue_growth": revenue_growth,
        "ebitda_margins": ebitda_margins,
        "capex_pcts": capex_pcts,
        "nwc_pcts": nwc_pcts,
    },
    "projections": {
        "year": projections['year'],
        "revenue_m": projections['revenue'],
        "ebitda_m": projections['ebitda'],
        "fcf_m": projections['fcf'],
    },
    "valuation": {
        "enterprise_value_m": ev_results['enterprise_value'],
        "pv_fcf_m": ev_results['pv_fcf'],
        "pv_terminal_m": ev_results['pv_terminal'],
        "terminal_pct": ev_results['terminal_percent'],
        "equity_value_m": equity_results['equity_value'],
        "value_per_share": equity_results['value_per_share'],
    },
    "sensitivity": {
        "wacc_range": wacc_range,
        "tg_range": tg_range,
        "matrix": sensitivity_matrix,
    },
    "scenarios": scenarios,
    "margin_of_safety": {
        "fair_value": equity_results['value_per_share'],
        "buy_at_85": equity_results['value_per_share'] * 0.85,
        "buy_at_80": equity_results['value_per_share'] * 0.80,
    }
}

# 寫入 JSON
with open('googl_dcf_output.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)

print(f"\n✅ 分析完成！結果已寫入 googl_dcf_output.json")

# ── 最終摘要 ──────────────────────────────────────────────────
fair_value = equity_results['value_per_share']
upside = (fair_value - current_price) / current_price * 100

print(f"\n{'='*60}")
print(f"  📌 GOOGL 核心結論")
print(f"{'='*60}")
print(f"  當前股價:    ${current_price:.2f}")
print(f"  DCF 內在價值: ${fair_value:.2f}")
print(f"  折溢價:      {upside:+.1f}%")
print(f"  85折安全邊際: ${fair_value * 0.85:.2f}")
print(f"  80折安全邊際: ${fair_value * 0.80:.2f}")
print(f"\n  情境分析:")
for name, s in scenarios.items():
    s_upside = (s['value_per_share'] - current_price) / current_price * 100
    print(f"    {name}: ${s['value_per_share']:.2f} ({s_upside:+.1f}%)")
print(f"{'='*60}")
