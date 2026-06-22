from typing import Optional

from pydantic import BaseModel, Field


class InputModel(BaseModel):
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


class SecretsModel(BaseModel):
    """
    Optional OneData credentials. When both are provided, input paths using the
    'onedata:///...' scheme are read from the SPICE OneData store. When absent,
    the piece reads from the local filesystem exactly as before.
    """

    onedata_onezone_host: Optional[str] = Field(
        default=None,
        description="Onedata Onezone host, e.g. data.spice-platform.eu"
    )
    onedata_token: Optional[str] = Field(
        default=None,
        description="Onedata access token."
    )
    onedata_output_dir: Optional[str] = Field(
        default=None,
        description="OneData base dir for outputs, e.g. onedata:///FilipsSpace/run"
    )


class OutputModel(BaseModel):
    """
    Output model for Fetch Energy Data Piece
    """

    message: str = Field(default="")
    output_path: str = Field(default="")
