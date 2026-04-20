import pandas as pd
import joblib
from pathlib import Path
from src.logger import logger

def generate_submission(
    model_path: Path,
    feature_table_path: Path,
    sample_submission_path: Path,
    output_dir: Path,
    verbose: bool = True
):
    """
    Generates a submission file by mapping predictions to sample_submission.csv.
    Ensures strict adherence to competition output format.
    """
    if verbose:
        logger.info(f"  🔮 Generating Predictions...")

    # 1. Load Artifacts
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found at {model_path}")
    model = joblib.load(model_path)
    
    if not feature_table_path.exists():
        raise FileNotFoundError(f"Feature table not found at {feature_table_path}")
    features_df = pd.read_csv(feature_table_path)
    features_df["Date"] = pd.to_datetime(features_df["Date"])
    
    if not sample_submission_path.exists():
        raise FileNotFoundError(f"Sample submission not found at {sample_submission_path}")
    sample_df = pd.read_csv(sample_submission_path)
    sample_df["Date"] = pd.to_datetime(sample_df["Date"])

    # 2. Match Features to Sample Submission Dates
    # We only predict for dates present in the sample submission
    test_features = sample_df[["Date"]].merge(features_df, on="Date", how="left")
    
    # Identify feature columns (exclude non-feature columns)
    drop_cols = ["Date", "Revenue", "COGS"]
    feature_cols = [c for c in test_features.columns if c not in drop_cols]
    
    X_test = test_features[feature_cols]
    
    # Handle missing features for future dates (e.g., fill with 0 or last known)
    X_test = X_test.fillna(0)

    # 3. Predict
    preds = model.predict(X_test)
    
    # 4. Create Submission File
    submission = sample_df.copy()
    submission["Revenue"] = preds
    
    # COGS is also usually required in the sample
    if "COGS" in submission.columns:
        # If model only predicts revenue, we might need a separate COGS model or simple ratio
        # For now, let's assume COGS is 0 or needs to be handled
        submission["COGS"] = submission["COGS"].fillna(0)

    output_path = output_dir / "submission.csv"
    submission.to_csv(output_path, index=False)
    
    if verbose:
        logger.info(f"  ✅ Prediction complete!")
        logger.info(f"  📊 Predicted for {len(submission)} rows.")
        logger.info(f"  💾 Submission saved to: {output_path}")

    return submission

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    generate_submission(
        project_root / "models/xgboost_revenue_model.joblib",
        project_root / "data/output/processed_features.csv",
        project_root / "data/raw/sample_submission.csv",
        project_root / "data/output"
    )
