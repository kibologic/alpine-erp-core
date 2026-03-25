# DIRECTIVE — alpine-erp-core
> Owner: Kibologic · Repo: kibologic/alpine-erp-core · License: BSL 1.1

---

## Architecture

This is the **open-core standalone product**.

- POS, Inventory, Dashboard, Users, Settings — all free modules live here
- Enterprise extensions live in `kibologic/alpine-erp` (BSL 1.1)
- Framework: SwissJS (`kibologic/swiss-lib`)

### Module tiers (this repo)
```
Free:       dashboard, users (cap 5), settings, pos, inventory
Enterprise: — (live in alpine-erp)
```

---

## Status

`ACTIVE` — synced from alpine-erp on 2026-03-14.

Includes:
- Full POS terminal (offline gate, session management, product grid, checkout)
- Inventory module
- 5-color palette dark theme
- CG-06 async reactivity fix (in swiss-lib, applied via pnpm override)
- Module registry pattern (open-core only)

---

## Session Protocol

1. Read this file
2. State current task
3. Build
4. Update this file at end of session

---

## Notes

- Do not add enterprise module imports to `App.uix` — those live in `alpine-erp`.
- `DEV_ENTERPRISE = false` is correct for this repo.

---

## Sprint — UI Component Library + Stock Take (Session current)

### Completed
- Integrated @alpine/ui component library (kibologic/alpine-ui)
- Rebuilt PosProductsPage.uix using DataTable, PageHeader, DataImport
- Rebuilt InventoryItemsPage.uix using DataTable, PageHeader
- Created StockTakePage.uix — in-app stock count, split layout, draggable summary modal
- Created StockTakeImportPage.uix — Excel import flow using DataImport.uix
- Created StockMovementsPage.uix — movement history, searchable DataTable
- Updated inventory module nav — Items, Stock Take, Import Stock Take, Stock Movements

### Open Issues
- Modal close/X/ESC fix — Phase 1 pending
- CG-08 — Draggable modals: document.addEventListener in mounted() — needs verification

## Sprint — POS Refinements + ECharts (Current)

### POS-F01 — Terminal Fullscreen Modes
Location: `modules/pos/src/pages/PosTerminalPage.uix`
- Mode 1: App-level fullscreen — hide both sidebars + topbar via CSS class on body
- Mode 2: Browser fullscreen via `document.documentElement.requestFullscreen()`
- Toggle button on terminal page header
- ESC key exits both modes
Status: COMPLETE

### POS-F02 — Global Quick Sale Widget  
Location: `apps/server/app/src/Shell.uix`
- Floating button bottom-left, visible on all non-terminal pages
- Click → opens quick sale modal reusing terminal UI components
- Status: COMPLETE (UI placeholder, wiring pending)

### Dashboard — ECharts Integration
Location: `modules/dashboard/src/pages/DashboardPage.uix`
- Replaced static bars with real `BarChart` and `LineChart` (Apache ECharts)
- Integrated via `@alpine/ui` base Chart component
- Status: COMPLETE

---

## Session Log

### 2026-03-24
#### Completed
- feat(gbil-integration): replaced core/events.py stub with gbil-events wrapper — publish_event/on_event API unchanged, Event now carries tenant_id
- feat(gbil-integration): added GbilError exception handler to core/exceptions.py
- feat(gbil-integration): created core/config.py (AppConfig subclassing GbilConfig)
- feat(gbil-integration): wired gbil-logger in main.py lifespan — structured JSON/dev output from startup
- feat(gbil-integration): created core/realtime.py — gbil-realtime server, wildcard bus→WebSocket bridge
- feat(gbil-integration): added /ws WebSocket endpoint to main.py (tenant_id query param)
- feat(gbil-integration): publish_event calls added to POS service (pos.session.open/close, pos.sale.created/refunded)
- feat(gbil-integration): publish_event calls added to inventory service (inventory.stock.adjusted)
- chore(deps): gbil packages + pydantic-settings + structlog + websockets added to requirements.txt
- fix(gbil-logger): removed add_logger_name processor (PrintLogger has no .name attr) — pushed to gbil repo
- fix(gbil-namespace): removed empty gbil/__init__.py from all 5 packages — pushed to gbil repo

### 2026-03-23
#### Completed
- Removed duplicated `shell.css` and `tokens.css` from public styles as `@skltn/shell` now owns them.
- Updated `dev.mjs` to natively serve `@skltn/shell` CSS files statically via Express.
- Renamed all UI component classes to `skltn-` namespace and consolidated `shell.css` with a stable fixed-position layout.
- Verified final shell rendering and positioning of Header, AppStrip, and NavPanel on port 3000.
- fix(inventory): replaced 📦 placeholder with professional SVG icon (ee14d0c).
- fix(shell): stable fixed-positioning, fixed app-nav offset, and robust SVG/Emoji icon rendering (3174cce).

### 2026-03-22
#### Completed
- feat(auth): POST /api/v1/auth/login + /refresh — f33ee88
- feat(tenant): GET /api/v1/tenant/{id}/config — 98c71e7
- feat(users): GET /api/v1/users/{id}/role — 1c28df1
- feat(inventory): GET /api/v1/inventory/stock-take/export (E-01) — 1bc524b
- feat(inventory): POST /api/v1/inventory/stock-take/import (E-02) — ceb7ea3
- chore(deps): python-multipart + openpyxl added to requirements.txt — bd9b258
- feat(inventory): POST/PATCH/DELETE /api/v1/inventory/categories — fd29597
- feat(inventory): GET/POST/PATCH /api/v1/inventory/suppliers — 00c1f92
- feat(users): POST /api/v1/users/invite + PATCH /api/v1/users/{id}/role — 694bb1a

#### Open Issues
- User.password_hash missing — login accepts any password, migration needed before production
- User.name missing — invite accepts name field but ignores it, migration needed
- User.updated_at missing — role updates have no timestamp
- Category.description missing — no backing column, migration needed if frontend requires it
- Auth tokens stored in-memory — will reset on uvicorn restart, needs DB-backed token table
- Suppliers table has no seed data

### 2026-03-25
#### Completed
- feat(auth): POST /api/v1/auth/mobile/login + /mobile/refresh — JWT endpoints for alpine-mobile
- feat(deps): python-jose[cryptography]==3.3.0 added to requirements.txt
- feat(migrations): 20260325_add_mobile_tables — stock_take_sessions, stock_take_counts, approvals, push_tokens, media
- feat(ws): WebSocket endpoint /ws/register/{register_id} — JWT auth via ?token=, tenant-scoped fan-out, 35s heartbeat timeout
- feat(mobile): stock-take endpoints (active, count, progress), approvals (list, detail, decision), push register, media upload, dashboard pulse
