import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from src.logger import logger

# 1. Reproducibility: Set Random Seed
np.random.seed(42)

def train_revenue_model(
    feature_table_path: Path,
    model_output_dir: Path,
    report_output_dir: Path,
    verbose: bool = True
):
    """
    Trains an XGBoost Regressor to predict Daily Revenue.
    Follows Datathon rules:
    - Time-Series Split for validation.
    - Export Feature Importance.
    - Reproducible results (Random Seed).
    """
    if verbose:
        logger.info(f"  🧠 Starting Model Training (XGBoost Regressor)...")

    # 2. Load Data
    if not feature_table_path.exists():
        raise FileNotFoundError(f"Feature table not found at {feature_table_path}")
    
    df = pd.read_csv(feature_table_path)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date") # Ensure chronological order for Time-Series Split

    # Define Target and Features
    target = "Revenue"
    # Exclude columns that are not features
    drop_cols = ["Date", "Revenue", "COGS"]
    features = [c for c in df.columns if c not in drop_cols]
    
    X = df[features]
    y = df[target]

    if verbose:
        logger.info(f"     Target: {target}")
        logger.info(f"     Features: {len(features)}")
        logger.info(f"     Total days: {len(df)}")

    # 3. Time-Series Split (K-Fold for Time Series)
    tscv = TimeSeriesSplit(n_splits=5)
    
    scores = []
    
    # 4. Training Loop with Cross-Validation
    # Note: For the final model, we will train on all data up to the last validation set
    for fold, (train_index, val_index) in enumerate(tscv.split(X)):
        X_train, X_val = X.iloc[train_index], X.iloc[val_index]
        y_train, y_val = y.iloc[train_index], y.iloc[val_index]
        
        # Setup XGBoost Regressor
        model = xgb.XGBRegressor(
            n_estimators=1000,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            n_jobs=-1,
            random_state=42,
            early_stopping_rounds=50
        )
        
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False
        )
        
        preds = model.predict(X_val)
        mae = mean_absolute_error(y_val, preds)
        rmse = np.sqrt(mean_squared_error(y_val, preds))
        r2 = r2_score(y_val, preds)
        
        scores.append(mae)
        if verbose:
            logger.info(f"     Fold {fold+1} | MAE: {mae:,.2f} | RMSE: {rmse:,.2f} | R2: {r2:.4f}")

    avg_mae = np.mean(scores)
    if verbose:
        logger.info(f"  ✅ Cross-Validation Complete. Avg MAE: {avg_mae:,.2f}")

    # 5. Final Model (Train on most data)
    final_model = xgb.XGBRegressor(
        n_estimators=500, # Use best params or fixed for stability
        learning_rate=0.05,
        max_depth=5,
        random_state=42
    )
    final_model.fit(X, y)

    # 6. Save Model Artifact
    model_output_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_output_dir / "xgboost_revenue_model.joblib"
    joblib.dump(final_model, model_path)
    
    if verbose:
        logger.info(f"  💾 Model saved to: {model_path}")

    # 7. Feature Importance Visualization
    plt.figure(figsize=(10, 6))
    importance_df = pd.DataFrame({
        "Feature": features,
        "Importance": final_model.feature_importances_
    }).sort_values("Importance", ascending=False)
    
    sns.barplot(data=importance_df.head(15), x="Importance", y="Feature", palette="viridis")
    plt.title("Top 15 Feature Importances (Daily Revenue Prediction)")
    plt.tight_layout()
    
    report_output_dir.mkdir(parents=True, exist_ok=True)
    plot_path = report_output_dir / "feature_importance.png"
    plt.savefig(plot_path)
    plt.close()
    
    if verbose:
        logger.info(f"  📊 Feature Importance plot saved to: {plot_path}")

    return final_model

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    train_revenue_model(
        project_root / "data/output/processed_features.csv",
        project_root / "models",
        project_root / "reports"
    )
