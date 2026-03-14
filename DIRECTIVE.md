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

- Every session starts by reading this file.
- Do not add enterprise module imports to `App.uix` — those live in `alpine-erp`.
- `DEV_ENTERPRISE = false` is correct for this repo.
