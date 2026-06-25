from typing import Optional

try:
    from common.onedata_models import OneDataSecretsModel, RunIdInputMixin
except ModuleNotFoundError:
    from pieces.common.onedata_models import OneDataSecretsModel, RunIdInputMixin


from pydantic import BaseModel, Field


class InputModel(RunIdInputMixin):
    history_csv: str = Field(description="Long-term history CSV path (local or 'onedata:///...')")
    updates_dir: str = Field(description="Folder with new delivered CSV files (local or 'onedata:///...')")
    archive_dir: str = Field(description="Archive folder for already processed files (local or 'onedata:///...')")
    bootstrap_parquet: str | None = Field(default=None, description="Optional parquet for first run bootstrap")


class SecretsModel(OneDataSecretsModel):
    pass



class OutputModel(BaseModel):
    message: str
    history_csv_out: str
    rows_total: int
    departments: list[str]
