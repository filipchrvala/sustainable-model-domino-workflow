from typing import Optional

from pydantic import BaseModel, Field


class InputModel(BaseModel):
    history_csv: str = Field(description="Long-term history CSV path (local or 'onedata:///...')")
    updates_dir: str = Field(description="Folder with new delivered CSV files (local or 'onedata:///...')")
    archive_dir: str = Field(description="Archive folder for already processed files (local or 'onedata:///...')")
    bootstrap_parquet: str | None = Field(default=None, description="Optional parquet for first run bootstrap")


class SecretsModel(BaseModel):
    """Optional OneData credentials; absent => local filesystem (unchanged)."""

    onedata_onezone_host: Optional[str] = Field(
        default=None, description="Onedata Onezone host, e.g. data.spice-platform.eu"
    )
    onedata_token: Optional[str] = Field(
        default=None, description="Onedata access token."
    )


class OutputModel(BaseModel):
    message: str
    history_csv_out: str
    rows_total: int
    departments: list[str]
