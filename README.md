# Antigravity Finance - US Stock Quant Dashboard

A dynamic, real-time US Stock Portfolio Management and Valuation War Room. This application leverages FastAPI for a high-performance backend, calculating real-time Discounted Cash Flow (DCF) models, and uses React + Vite for a premium, highly responsive frontend dashboard.

## 🌟 Key Features

* **Real-time Portfolio Sync:** Directly integrates with Google Sheets API to pull the latest transaction records, current pricing, and sector/quadrant allocation data without any manual caching overhead.
* **Valuation Lab (DCF Engine):** 
  * Automatically fetches the latest financial data and SEC filings via `yfinance`.
  * Computes Weighted Average Cost of Capital (WACC), Terminal Growth, and Beta.
  * Projects future cash flows and calculates an exact Intrinsic Value / Share and a discounted Margin of Safety (MoS) target price.
* **Premium Dashboard UI:** Built with React, Tailwind CSS v4, and Recharts, structured beautifully with Shadcn-like components to provide actionable, easy-to-read financial breakdowns.

## 🛠 Tech Stack

* **Frontend:** React, Vite, Tailwind CSS v4, Recharts, Lucide React, Shadcn/ui
* **Backend:** Python, FastAPI, Uvicorn, Pandas, yfinance, gspread (Google Sheets API)

## 🚀 Getting Started

### Prerequisites
* Node.js & npm (for frontend)
* Python 3.9+ (for backend)
* Google Cloud Service Account Credentials (`us-stock-*.json`) with access to the target Google Sheet.

### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install fastapi uvicorn gspread google-auth pandas yfinance numpy
   ```
4. Place your Google Service Account JSON file in the project root map (it is `.gitignore`d automatically to prevent secrets leaking).
5. Run the FastAPI development server:
   ```bash
   python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the Vite development server:
   ```bash
   npm run dev
   ```

## 🔒 Security Note
Do **NOT** commit your Google Service account `.json` to version control. The repository includes a `.gitignore` tailored to exclude API tokens, local `.env` variables, and Python caches.
