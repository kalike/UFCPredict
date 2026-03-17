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

## Routers (estado F2 MVP)

| Router | Endpoints clave | Estado |
|---|---|---|
| `system` | /api/system/health, /registry | ✅ |
| `scraping` | /api/scraping/{start,status,runs} | ✅ (UFCStats → DB, sin JSON) |
| `publish` | /api/publish/dry-run, /runs | ✅ (CLI wrapper, real run en F4) |
| `models` | /api/models, /train, versions activate/mark/delete | ✅ (training stub) |
| `hp-search` | /api/hp-search/start, studies, trials | ✅ (worker stub) |
| `combo-search` | /api/combo-search/start, studies, trials | ✅ (worker stub) |
| `fighters` | /api/fighters list + detail | ✅ |
| `compare` | /api/compare?a=&b= | ✅ |
| `predictions` | /api/predictions/events, /cache/{event_id} | ✅ (sin inference real) |

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

## Pendiente (post-F2)

- Worker real de training (integra `ufc_core.trainer.core`)
- Worker real de HP search (Optuna)
- Worker real de combo search
- Endpoint predict-future con inference de ensemble + TTA
- Recalculation router
- WebSockets para HP/combo monitoring (UI live updates)
- Lab UI (apps/lab-ui/) — siguiente sub-fase de F2
