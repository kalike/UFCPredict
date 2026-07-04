# UFC Lab

Plataforma de predicción de peleas UFC: entrenamiento de modelos ML,
dashboard de métricas y sistema de apuestas.

## Estructura

- `packages/ufc_core` — paquete compartido: modelos SQLAlchemy, feature engine,
  entrenamiento/inferencia, scrapers (UFCStats, Tapology) y betting engine.
- `apps/lab-api` — API FastAPI (puerto 8101): training, gestión de versiones,
  predicciones, scraping y dashboard.
- `apps/lab-ui` — frontend React 19 + Vite + Tailwind (puerto 5174).

## Requisitos

- Python >= 3.13
- Node 20+
- PostgreSQL 16

## Setup

```bash
# Core + API (editable)
pip install -e packages/ufc_core -e apps/lab-api

# DB: crear base y aplicar migraciones
createdb ufc_lab
cd packages/ufc_core && alembic upgrade head

# UI
cd apps/lab-ui && npm install
```

Conexión a DB vía variables `UFC_LAB_DB_HOST/PORT/NAME/USER/PASS`
(o `DATABASE_URL` directamente).

## Arranque

```bash
# API
uvicorn lab_api.main:app --port 8101 --reload

# UI
cd apps/lab-ui && npm run dev
```

La UI espera la API en `localhost:8101`.

## Tests

```bash
pytest packages/ufc_core apps/lab-api
```

Los tests e2e de scraping están gateados por red (se saltan sin conexión).
