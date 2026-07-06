
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece
from .models import InputModel, OutputModel
from pathlib import Path
import pandas as pd
import traceback


class PreprocessEnergyDataPiece(BasePiece):
    """
    Prepare training data only (train_dataset.parquet).
    The prediction input for PredictPiece is a separate CSV and is not generated here.
    """

    def piece_function(self, input_data: InputModel) -> OutputModel:
        log_path = Path(self.results_path) / "preprocess_energy_data.log"
        err_path = Path(self.results_path) / "preprocess_energy_data_error.txt"
        try:
            print("[INFO] PreprocessEnergyDataPiece started")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("[INFO] PreprocessEnergyDataPiece started\n")

            input_path = Path(input_data.input_path)
            generate_predict = getattr(input_data, "generate_predict_dataset", False)

            print(f"[INFO] Using input file: {input_path}")
            print(f"[INFO] generate_predict_dataset: {generate_predict}")

            if not input_path.exists():
                raise FileNotFoundError(f"Input file not found: {input_path}")

            df = pd.read_parquet(input_path)

            if "datetime" not in df.columns:
                raise ValueError(f"Input must contain datetime column. Found: {df.columns}")

            df["datetime"] = pd.to_datetime(df["datetime"])
            if "department_id" in df.columns:
                df = df.drop_duplicates(subset=["department_id", "datetime"])
            else:
                df = df.drop_duplicates(subset=["datetime"])
            df = df.sort_values("datetime")
            df = df.set_index("datetime")

            if "department_id" in df.columns:
                parts = []
                for dept, g in df.groupby("department_id"):
                    g2 = g.drop(columns=["department_id"]).resample("15min").mean().ffill()
                    g2["department_id"] = dept
                    parts.append(g2.reset_index())
                train_df = pd.concat(parts, ignore_index=True).sort_values(["department_id", "datetime"]).reset_index(drop=True)
            else:
                df_15min = df.resample("15min").mean().ffill()
                train_df = df_15min.reset_index()
            train_df.rename(columns={"index": "datetime"}, inplace=True)

            train_path = Path(self.results_path) / "train_dataset.parquet"
            train_df.to_parquet(train_path, index=False)

            print("[SUCCESS] Preprocessing finished (train_dataset only)")
            print(f"[INFO] Train rows: {len(train_df)}")

            predict_path_str = ""
            if generate_predict:
                print("[WARN] generate_predict_dataset=True is deprecated here; use separate CSV for PredictPiece.")

            self.display_result = {"file_type": "parquet", "file_path": str(train_path)}

            return OutputModel(
                message="Preprocessing finished (train_dataset only)",
                train_file_path=str(train_path),
                predict_file_path=predict_path_str,
            )
        except Exception:
            err = traceback.format_exc()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("[ERROR] PreprocessEnergyDataPiece failed\n")
                f.write(err + "\n")
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(err)
            raise
