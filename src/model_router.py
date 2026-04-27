from pathlib import Path

from src.logger import logger
from src.predictor import generate_submission as generate_arima_hybrid_submission
from src.seasonal_xgb_predictor import generate_seasonal_xgb_submission
from src.seasonal_xgb_trainer import train_seasonal_xgb_model
from src.trainer import train_revenue_model as train_arima_hybrid_model

SUPPORTED_MODEL_ARCHITECTURES = ("arima_hybrid", "seasonal_xgb_ratio")


def validate_model_architecture(model_arch: str) -> str:
    if model_arch not in SUPPORTED_MODEL_ARCHITECTURES:
        raise ValueError(
            f"Unsupported model architecture '{model_arch}'. "
            f"Choose one of: {', '.join(SUPPORTED_MODEL_ARCHITECTURES)}"
        )
    return model_arch


def train_model_architecture(
    model_arch: str,
    feature_table_path: Path,
    model_output_dir: Path,
    report_output_dir: Path,
    train_until: str | None = None,
    verbose: bool = True,
):
    model_arch = validate_model_architecture(model_arch)
    logger.info(f"  🧠 Active model architecture: {model_arch}")

    if model_arch == "arima_hybrid":
        return train_arima_hybrid_model(
            feature_table_path=feature_table_path,
            model_output_dir=model_output_dir,
            report_output_dir=report_output_dir,
            train_until=train_until,
            verbose=verbose,
        )

    if model_arch == "seasonal_xgb_ratio":
        return train_seasonal_xgb_model(
            feature_table_path=feature_table_path,
            model_output_dir=model_output_dir,
            report_output_dir=report_output_dir,
            train_until=train_until,
            verbose=verbose,
        )

    raise AssertionError(f"Unhandled model architecture: {model_arch}")


def generate_submission_for_architecture(
    model_arch: str,
    model_path: Path,
    feature_table_path: Path,
    sample_submission_path: Path,
    output_dir: Path,
    cogs_model_path: Path | None = None,
    verbose: bool = True,
):
    model_arch = validate_model_architecture(model_arch)
    logger.info(f"  🧠 Active model architecture: {model_arch}")

    if model_arch == "arima_hybrid":
        return generate_arima_hybrid_submission(
            model_path=model_path,
            feature_table_path=feature_table_path,
            sample_submission_path=sample_submission_path,
            output_dir=output_dir,
            cogs_model_path=cogs_model_path,
            verbose=verbose,
        )

    if model_arch == "seasonal_xgb_ratio":
        return generate_seasonal_xgb_submission(
            model_dir=model_path.parent,
            feature_table_path=feature_table_path,
            sample_submission_path=sample_submission_path,
            output_dir=output_dir,
            verbose=verbose,
        )

    raise AssertionError(f"Unhandled model architecture: {model_arch}")
