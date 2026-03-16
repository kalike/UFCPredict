"""
UFC Predictor — Schemas for the scraping router.
"""

from pydantic import BaseModel


class ScrapingStartResponse(BaseModel):
    ok: bool
    message: str


class ScrapingStatusResponse(BaseModel):
    status: str  # idle | running | completed | error
    step: str
    progress_letter: str
    progress_current: int
    progress_total: int
    letters_done: int
    log_lines: list[str]
    started_at: str | None
    finished_at: str | None
    error: str | None
    result: dict | None


class BackupInfo(BaseModel):
    filename: str
    size_mb: float
    created: str


class BackupListResponse(BaseModel):
    backups: list[BackupInfo]


class RestoreBackupResponse(BaseModel):
    ok: bool
    message: str
    fighters_loaded: int


class PhotosStatusResponse(BaseModel):
    """Status payload for the photo-scraping pipeline."""
    status: str  # idle | running | completed | error
    step: str
    progress_current: int
    progress_total: int
    log_lines: list[str]
    started_at: str | None
    finished_at: str | None
    error: str | None
    result: dict | None
