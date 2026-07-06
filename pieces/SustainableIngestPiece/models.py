from pydantic import BaseModel, Field


class InputModel(BaseModel):
    history_csv: str = Field(description="Long-term history CSV path")
    updates_dir: str = Field(description="Folder with new delivered CSV files")
    archive_dir: str = Field(description="Archive folder for already processed files")
    bootstrap_parquet: str | None = Field(default=None, description="Optional parquet for first run bootstrap")


class OutputModel(BaseModel):
    message: str
    history_csv_out: str
    rows_total: int
    departments: list[str]
