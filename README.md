# Alpine ERP Core

Open-core ERP. MIT licensed.

## Modules included
- **POS** — Point of sale, cash sessions, payments
- **Inventory** — Products, categories, stock movements

## Enterprise modules
Available in [alpine-erp](https://github.com/kibologic/alpine-erp) (BSL 1.1):
Finance, HR, Payroll, Sales, Procurement, AI agentic layer

## Stack
- Frontend: SwissJS `.ui`/`.uix` — [swiss-lib](https://github.com/kibologic/swiss-lib)
- Backend: FastAPI + asyncpg
- Database: PostgreSQL
- Dev server: [Swite](https://github.com/kibologic/swite)

## Getting started
```bash
git clone https://github.com/kibologic/alpine-erp-core
cd alpine-erp-core
pnpm install
# Start PostgreSQL
cp services/.env.example services/.env
cd services && python3 -m uvicorn main:app --reload --port 8000
pnpm dev
```
