# lab-api

FastAPI local para el lab de UFC: training, monitorización, gestión de versiones, scraping. Puerto 8101.

Importa `ufc_core` (paquete compartido, `packages/ufc_core/`).

## Arranque

```bash
pip install -e packages/ufc_core/[dev]
pip install -e apps/lab-api/[dev]

UFC_LAB_DB_USER=ufc UFC_LAB_DB_PASS=ufc_secret lab-api
```

lab-api escucha en :8101.

## Routers (estado F2 maduro)

| Router | Endpoints clave | Estado |
|---|---|---|
| `system` | /api/system/health, /registry | ✅ |
| `models` | /api/models, /train, versions activate/mark/delete | ✅ training real (LGBM/XGB/LR), otros stub |
| `predictions` | /api/predictions/events, /event/{id}/predict, /cache/{id} | ✅ inference ensemble simple |
| `scraping` | /api/scraping/{start,status,runs} | ✅ + tapology hook + materialización features automáticos |
| `publish` | /api/publish/dry-run, /runs | ✅ (CLI wrapper, real run en F4) |
| `hp-search` | /api/hp-search/start, studies, trials | ✅ (worker stub) |
| `combo-search` | /api/combo-search/start, studies, trials | ✅ (worker stub) |
| `fighters` | /api/fighters list + detail | ✅ |
| `compare` | /api/compare?a=&b= | ✅ |

## Tests

```bash
UFC_LAB_DB_USER=ufc UFC_LAB_DB_PASS=ufc_secret \
pytest apps/lab-api/tests/
```

Para correr ambas suites juntas (ufc_core + lab-api) desde la raíz del monorepo:

```bash
UFC_LAB_DB_USER=ufc UFC_LAB_DB_PASS=ufc_secret \
pytest packages/ufc_core/tests/ apps/lab-api/tests/
```

## Pendiente (post-F2 maduro)

- Worker real de HP search (Optuna)
- Worker real de combo search
- Training para modelos restantes (RF, SVM, MLP, Deep, RNet, Ens3)
- TTA + weighted ensemble en inference
- Recalculation router
- WebSockets para HP/combo monitoring (UI live updates)
