"""Typed, local-only configuration for the POC.

No network defaults exist anywhere in this module, per the offline/local-only
constraint (docs/00-development-requirements-spec.md header,
docs/05-technology-decision-matrix.md). All paths resolve to local
directories under the repo root; overrides come from environment variables
or a local .env file, never a remote config service.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DSFS_", env_file=".env", extra="ignore")

    data_raw_dir: Path = Field(default=REPO_ROOT / "data" / "raw")
    data_interim_dir: Path = Field(default=REPO_ROOT / "data" / "interim")
    data_processed_dir: Path = Field(default=REPO_ROOT / "data" / "processed")
    schema_dir: Path = Field(default=REPO_ROOT / "docs" / "schemas")
    reports_dir: Path = Field(default=REPO_ROOT / "reports")

    # Extraction stage (docs/05, docs/07): OPEN item — exact model/runtime
    # pending a local feasibility check (docs/14-open-questions.md, item 1).
    # When unset, the extraction pipeline uses the documented degradation
    # baseline (regex + supplied-mention matching, no statistical NER/LLM).
    local_llm_model_path: Path | None = None
    llm_extraction_enabled: bool = False

    def ensure_dirs(self) -> None:
        for d in (self.data_raw_dir, self.data_interim_dir, self.data_processed_dir, self.reports_dir):
            d.mkdir(parents=True, exist_ok=True)


@cache
def get_settings() -> Settings:
    return Settings()
