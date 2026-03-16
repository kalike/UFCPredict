# ufc_core

Paquete Python compartido por las apps del lab.

Núcleo DB-only: dominio, features, entrenamiento, inferencia, scrapers y betting.

## Instalación (modo dev)

```bash
pip install -e packages/ufc_core/[dev]
```

## Base de datos

Crea la base `ufc_lab` y aplica el schema completo:

```bash
UFC_LAB_DB_USER=ufc UFC_LAB_DB_PASS=ufc_secret \
bash scripts/create-ufc-lab-db.sh
```

## Tests

```bash
UFC_LAB_DB_USER=ufc UFC_LAB_DB_PASS=ufc_secret \
pytest packages/ufc_core/
```

Para el smoke de red (scrape real contra UFCStats):

```bash
UFC_LAB_DB_USER=ufc UFC_LAB_DB_PASS=ufc_secret UFC_RUN_NETWORK_TESTS=1 \
pytest packages/ufc_core/tests/integration/
```

## CLI

```bash
ufc-publish --help
```

## Estado F1

| Área | Estado |
|---|---|
| db schema (30 tablas) + alembic | ✅ |
| feature store materializado | ✅ |
| scrapers UFCStats / Tapology / fotos | ✅ |
| tapology subsystem (orchestrator/picks/match) | ✅ |
| ModelRegistry DB-backed | ✅ |
| trainer / predictor / betting (importables) | ✅ |
| ufc-publish --dry-run | ✅ |
| smoke e2e network test | ✅ (gated) |

Funcionalidad ML completa de trainer/predictor está portada pero validada únicamente
a nivel de importabilidad. Tests behaviorales detallados llegarán con el lab-api (F2).

## NO está en F1

- Lab API ni Lab UI (F2)
- Explotación API ni UI (F3)
- IaC AWS / SageMaker / S3 (F4)
- `ufc-publish` execution real (F4)
