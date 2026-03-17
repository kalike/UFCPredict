"""Publish router — wraps ufc_core.publish.cli.

F1 scope: only dry-run is operational. F4 will wire S3/SageMaker/RDS execution.
"""

import io
import sys
from contextlib import redirect_stdout, redirect_stderr

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ufc_core.db import models as db_models

from lab_api.deps import get_db

router = APIRouter(prefix="/api/publish", tags=["publish"])


class DryRunRequest(BaseModel):
    version_id: int | None = None
    all_active: bool = False
    skip_data: bool = False
    target: str = "aws"  # "local" | "aws"


class DryRunResponse(BaseModel):
    rc: int
    plan_text: str


@router.post("/dry-run", response_model=DryRunResponse)
def publish_dry_run(req: DryRunRequest) -> DryRunResponse:
    """Show what `ufc-publish` would do without executing anything."""
    if not (req.version_id or req.all_active):
        raise HTTPException(400, "Provide version_id or set all_active=true")

    from ufc_core.publish.cli import main as cli_main

    argv = ["--dry-run", "--target", req.target]
    if req.skip_data:
        argv.append("--skip-data")
    if req.all_active:
        argv.append("--all-active")
    else:
        argv += ["--version-id", str(req.version_id)]

    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = cli_main(argv)
    return DryRunResponse(rc=rc, plan_text=buf.getvalue())


class PublishHistoryEntry(BaseModel):
    id: int
    model_version_id: int
    phase: str
    status: str
    ran_at: str


@router.get("/runs", response_model=list[PublishHistoryEntry])
def list_publish_runs(limit: int = 20, db: Session = Depends(get_db)) -> list[PublishHistoryEntry]:
    rows = (
        db.query(db_models.PublishRun)
          .order_by(db_models.PublishRun.ran_at.desc())
          .limit(limit)
          .all()
    )
    return [
        PublishHistoryEntry(
            id=r.id, model_version_id=r.model_version_id,
            phase=r.phase, status=r.status,
            ran_at=r.ran_at.isoformat() if r.ran_at else "",
        ) for r in rows
    ]
