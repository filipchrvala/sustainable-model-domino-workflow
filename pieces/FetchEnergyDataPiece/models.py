from typing import Optional

try:
    from common.onedata_models import OneDataSecretsModel, RunIdInputMixin
except ModuleNotFoundError:
    from pieces.common.onedata_models import OneDataSecretsModel, RunIdInputMixin


from pydantic import BaseModel, Field


class InputModel(RunIdInputMixin):
    """
    Input model for Fetch Energy Data Piece
    """

    load_csv: str = Field(
        default="/home/shared_storage/load.csv",
        description="Path to load CSV file or a directory with load*.csv files. "
                    "May be a local path or an 'onedata:///space/...' URL."
    )

    prices_csv: str = Field(
        default="/home/shared_storage/prices.csv",
        description="Path to prices CSV file (local path or 'onedata:///...' URL)."
    )


class SecretsModel(OneDataSecretsModel):
    pass



class OutputModel(BaseModel):
    """
    Output model for Fetch Energy Data Piece
    """
    run_id: str = Field(default="", description="Workflow run id for OneData output subfolder")

    message: str = Field(default="")
    output_path: str = Field(default="")
