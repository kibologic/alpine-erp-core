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
