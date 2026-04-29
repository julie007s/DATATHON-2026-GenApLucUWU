# ============================================================
# ██████████████  TÙY CHỈNH THAM SỐ TẠI ĐÂY  ██████████████
# ============================================================

import json
import os
import warnings

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
from mlforecast import MLForecast
from mlforecast.lag_transforms import RollingMax, RollingMean, RollingMin
from sklearn.metrics import mean_absolute_error, mean_squared_error

warnings.filterwarnings("ignore")
# Tắt log mặc định của Optuna (chỉ hiển thị kết quả quan trọng)
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ============================================================
# TUNING CONFIG — Tùy chỉnh tham số tại đây
# ============================================================
TUNING_CFG = {
    # --- Đường dẫn ---
    "input_path":       "../data/raw/sales.csv",
    "output_dir":       "../data/output",
    "best_params_file": "../models/optuna_best_params.json",  # Lưu kết quả tối ưu
    "submission_file":  "../data/output/submission_tuned.csv",

    # --- Dữ liệu ---
    "date_col":     "Date",
    "target_cols":  ["Revenue", "COGS"],
    "train_ratio":  0.70,            # 70% đầu → train CV; 30% cuối → held-out test

    # --- Cấu hình dự báo ---
    "forecast_horizon": 548,         # Số ngày dự báo thật (01/01/2023 → 01/07/2024)
    "forecast_start":   "2023-01-01",

    # --- Optuna ---
    "n_trials":    100,               # Số vòng thử (tăng lên 50-100 nếu máy mạnh)
    "cv_horizon":  548,              # Horizon của mỗi cửa sổ CV (bằng horizon thật)
    "cv_n_windows": 1,              # Số cửa sổ CV (tăng lên 2-3 nếu đủ dữ liệu)

    # --- Không gian tìm kiếm (Search Space) ---
    # Ghi chú: Optuna dùng Bayesian Optimization (TPE) để chọn thông minh
    "search_space": {
        "n_estimators":    {"type": "int",   "low": 300,  "high": 1500, "step": 1},
        "learning_rate":   {"type": "float", "low": 0.01, "high": 0.1,  "log": True},
        "max_depth":       {"type": "int",   "low": 3,    "high": 9},
        "num_leaves":      {"type": "int",   "low": 20,   "high": 120,  "step": 1},
        "min_child_samples": {"type": "int", "low": 10,   "high": 50},
        "subsample":       {"type": "float", "low": 0.6,  "high": 0.95},
        "colsample_bytree":{"type": "float", "low": 0.6,  "high": 0.95},
        "reg_alpha":       {"type": "float", "low": 0.0,  "high": 1.0},
        "reg_lambda":      {"type": "float", "low": 0.0,  "high": 1.0},
    },

    # --- Features cố định (không tối ưu hóa) ---
    # Giữ nguyên lag 354 và 365 — quan trọng cho chu kỳ Tết Âm/Dương lịch
    "lags": [1, 2, 3, 7, 14, 21, 30, 60, 90, 180, 354, 365],
    "rolling_windows": [7, 30],
    "date_features": ["dayofweek", "month", "day", "dayofyear"],

    # --- Gregorian Peak Dates (sự kiện Dương lịch cố định) ---
    "gregorian_peaks": [
        {"months": [2],  "days": range(12, 15)},   # Valentine / Pre-Tết
        {"months": [3],  "days": range(6,  9)},    # Quốc tế Phụ nữ
        {"months": [4],  "days": range(28, 31)},   # Trước lễ 30/04
        {"months": [5],  "days": [1]},             # Quốc tế Lao động
        {"months": [9],  "days": [1, 2]},          # Quốc khánh
        {"months": [12], "days": range(20, 32)},   # Mùa mua sắm cuối năm
    ],
}


# ============================================================
# BƯỚC 1: LOAD & CHUẨN BỊ DỮ LIỆU
# ============================================================

def load_long_format(cfg: dict) -> pd.DataFrame:
    """
    Đọc sales.csv và chuyển Wide → Long format chuẩn mlforecast
    (cột: unique_id, ds, y). Nội suy tuyến tính nếu có giá trị NULL.
    """
    df_wide = pd.read_csv(cfg["input_path"], parse_dates=[cfg["date_col"]])
    df_wide = df_wide.rename(columns={cfg["date_col"]: "ds"})

    # Nội suy nếu có giá trị thiếu
    missing = df_wide[cfg["target_cols"]].isnull().sum()
    if missing.any():
        print(f"⚠️  NULL values detected:\n{missing[missing > 0]}")
        df_wide[cfg["target_cols"]] = df_wide[cfg["target_cols"]].interpolate(
            method="linear"
        )

    # Wide → Long
    df_long = df_wide.melt(
        id_vars=["ds"],
        value_vars=cfg["target_cols"],
        var_name="unique_id",
        value_name="y",
    ).sort_values(["unique_id", "ds"]).reset_index(drop=True)

    return df_long


def temporal_split(df_long: pd.DataFrame, train_ratio: float):
    """
    Phân chia Long Format theo thứ tự thời gian (temporal split).
    Tránh random split để không gây data leakage.
    """
    all_dates = np.sort(df_long["ds"].unique())
    n_train   = int(len(all_dates) * train_ratio)
    cutoff    = pd.Timestamp(all_dates[n_train - 1])

    df_train = df_long[df_long["ds"] <= cutoff].reset_index(drop=True)
    df_test  = df_long[df_long["ds"] >  cutoff].reset_index(drop=True)
    return df_train, df_test, cutoff


# ============================================================
# BƯỚC 2: DATE FEATURE CALLABLE (is_gregorian_peak)
# ============================================================

def make_gregorian_peak_fn(peaks_cfg: list):
    """
    Factory: tạo callable tương thích mlforecast date_features.
    MLForecast gọi fn(DatetimeIndex) → pd.Series tại cả fit() lẫn predict().
    """
    # Vật liệu hóa range() trước để pickling dễ dàng hơn
    peaks = [{"months": list(p["months"]), "days": list(p["days"])} for p in peaks_cfg]

    def is_gregorian_peak(dates: pd.DatetimeIndex) -> pd.Series:
        day   = dates.day.to_numpy()
        month = dates.month.to_numpy()
        mask  = np.zeros(len(dates), dtype=np.int8)
        for rule in peaks:
            in_month = np.isin(month, rule["months"])
            in_day   = np.isin(day,   rule["days"])
            mask    |= (in_month & in_day).astype(np.int8)
        return pd.Series(mask, index=range(len(dates)), name="is_gregorian_peak")

    return is_gregorian_peak


# ============================================================
# BƯỚC 3: HÀM XÂY DỰNG LAG TRANSFORMS
# ============================================================

def build_lag_transforms(window_sizes: list, min_samples: int = 1) -> dict:
    """
    Tạo dict lag_transforms cho MLForecast:
        {lag: [RollingMean, RollingMax, RollingMin]}
    Mỗi window_size tạo 3 loại rolling transform (mean, max, min).
    """
    lag_transforms = {}
    for win in window_sizes:
        lag_transforms[win] = [
            RollingMean(window_size=win, min_samples=min_samples),
            RollingMax(window_size=win,  min_samples=min_samples),
            RollingMin(window_size=win,  min_samples=min_samples),
        ]
    return lag_transforms


# ============================================================
# BƯỚC 4: HÀM MỤC TIÊU OPTUNA (Objective)
# ============================================================

def build_objective(df_melted: pd.DataFrame, cfg: dict):
    """
    Factory trả về hàm objective(trial) cho Optuna.
    Đóng gói df_melted và cfg vào closure để tránh biến toàn cục.

    Quy trình mỗi trial:
      1. Optuna đề xuất bộ tham số mới (Bayesian/TPE)
      2. Xây dựng MLForecast với bộ tham số đó
      3. Chạy Time Series Cross-Validation (n_windows cửa sổ)
      4. Trả về RMSE trung bình → Optuna dùng để hướng dẫn trial tiếp theo
    """
    lag_transforms     = build_lag_transforms(cfg["rolling_windows"])
    gregorian_peak_fn  = make_gregorian_peak_fn(cfg["gregorian_peaks"])
    date_feats         = cfg["date_features"] + [gregorian_peak_fn]

    def objective(trial: optuna.Trial) -> float:
        ss = cfg["search_space"]

        # --- Optuna gợi ý tham số theo không gian tìm kiếm đã khai báo ---
        param = {
            "n_estimators":     trial.suggest_int(
                "n_estimators", ss["n_estimators"]["low"],
                ss["n_estimators"]["high"], step=ss["n_estimators"]["step"]
            ),
            "learning_rate":    trial.suggest_float(
                "learning_rate", ss["learning_rate"]["low"],
                ss["learning_rate"]["high"], log=ss["learning_rate"]["log"]
            ),
            "max_depth":        trial.suggest_int(
                "max_depth", ss["max_depth"]["low"], ss["max_depth"]["high"]
            ),
            "num_leaves":       trial.suggest_int(
                "num_leaves", ss["num_leaves"]["low"],
                ss["num_leaves"]["high"], step=ss["num_leaves"]["step"]
            ),
            "min_child_samples": trial.suggest_int(
                "min_child_samples", ss["min_child_samples"]["low"],
                ss["min_child_samples"]["high"]
            ),
            "subsample":        trial.suggest_float(
                "subsample", ss["subsample"]["low"], ss["subsample"]["high"]
            ),
            "colsample_bytree": trial.suggest_float(
                "colsample_bytree", ss["colsample_bytree"]["low"],
                ss["colsample_bytree"]["high"]
            ),
            "reg_alpha":        trial.suggest_float(
                "reg_alpha", ss["reg_alpha"]["low"], ss["reg_alpha"]["high"]
            ),
            "reg_lambda":       trial.suggest_float(
                "reg_lambda", ss["reg_lambda"]["low"], ss["reg_lambda"]["high"]
            ),
            "random_state": 42,
            "n_jobs": -1,
            "verbose": -1,
        }

        # --- Khởi tạo MLForecast với bộ tham số thử nghiệm ---
        fcst = MLForecast(
            models={"LightGBM": lgb.LGBMRegressor(**param)},
            freq="D",
            lags=cfg["lags"],
            lag_transforms=lag_transforms,
            date_features=date_feats,
            num_threads=4,
        )

        # --- Time Series Cross-Validation ---
        # h          : horizon mỗi cửa sổ (= 548 ngày — bằng horizon dự báo thật)
        # n_windows  : số lần lùi cửa sổ
        # step_size  : khoảng cách giữa các cửa sổ (mặc định = h)
        cv_res = fcst.cross_validation(
            df=df_melted,
            h=cfg["cv_horizon"],
            n_windows=cfg["cv_n_windows"],
            step_size=cfg["cv_horizon"],  # Không chồng lấp giữa các cửa sổ
        )

        # --- Tính RMSE trung bình trên tất cả unique_id ---
        # RMSE phạt nặng outlier → phù hợp với dữ liệu doanh thu có spike
        y_true = cv_res["y"].values
        y_pred = cv_res["LightGBM"].values
        rmse   = np.sqrt(mean_squared_error(y_true, y_pred))

        return rmse

    return objective


# ============================================================
# BƯỚC 5: CHẠY OPTUNA & LƯU KẾT QUẢ
# ============================================================

def run_tuning(cfg: dict) -> dict:
    """
    Chạy toàn bộ quá trình Optuna hyperparameter tuning.

    Returns
    -------
    dict chứa best_params
    """
    os.makedirs(cfg["output_dir"], exist_ok=True)
    os.makedirs(os.path.dirname(cfg["best_params_file"]), exist_ok=True)

    # --- Load dữ liệu ---
    print("📂 Đang tải dữ liệu...")
    df_long = load_long_format(cfg)
    print(f"   Shape: {df_long.shape} | "
          f"Từ {df_long['ds'].min().date()} đến {df_long['ds'].max().date()}")

    # Sử dụng toàn bộ df_long cho CV
    # (MLForecast cross_validation tự cắt cửa sổ theo h và n_windows)
    df_melted = df_long

    # --- Tạo hàm objective ---
    objective = build_objective(df_melted, cfg)

    # --- Tạo Study với TPE Sampler (Bayesian Optimization) ---
    sampler = optuna.samplers.TPESampler(seed=42)
    study   = optuna.create_study(
        direction="minimize",
        sampler=sampler,
        study_name="lgbm_mlforecast_tuning",
    )

    print(f"\n🔍 Bắt đầu Optuna với {cfg['n_trials']} trials...")
    print(f"   CV horizon    : {cfg['cv_horizon']} ngày x {cfg['cv_n_windows']} cửa sổ")
    print(f"   Metric tối ưu : RMSE (minimize)")
    print("-" * 60)

    study.optimize(
        objective,
        n_trials=cfg["n_trials"],
        show_progress_bar=True,
    )

    # --- Kết quả ---
    best_params = study.best_params
    best_rmse   = study.best_value

    print("\n" + "=" * 60)
    print("🎉 HOÀN THÀNH TỐI ƯU HÓA!")
    print(f"   RMSE tốt nhất : {best_rmse:,.2f}")
    print(f"   Bộ tham số tối ưu:")
    for k, v in best_params.items():
        print(f"     {k:<22}: {v}")
    print("=" * 60)

    # Thêm các tham số cố định vào best_params trước khi lưu
    best_params_full = {
        **best_params,
        "random_state": 42,
        "n_jobs": -1,
        "verbose": -1,
    }

    # Lưu ra JSON để dùng lại trong pipeline chính
    with open(cfg["best_params_file"], "w", encoding="utf-8") as f:
        json.dump(
            {"best_rmse_cv": best_rmse, "best_params": best_params_full},
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\n💾 Đã lưu best params → {cfg['best_params_file']}")

    return best_params_full


# ============================================================
# BƯỚC 6: TRAIN LẠI VỚI BEST PARAMS & XUẤT submission_tuned.csv
# ============================================================

def train_and_submit(best_params: dict, cfg: dict) -> None:
    """
    Dùng best_params từ Optuna để train trên 100% lịch sử,
    dự báo 548 ngày, và lưu submission_tuned.csv.
    """
    print("\n📦 Đang train mô hình cuối cùng với best params...")

    df_long           = load_long_format(cfg)
    lag_transforms    = build_lag_transforms(cfg["rolling_windows"])
    gregorian_peak_fn = make_gregorian_peak_fn(cfg["gregorian_peaks"])
    date_feats        = cfg["date_features"] + [gregorian_peak_fn]

    fcst = MLForecast(
        models={"LightGBM": lgb.LGBMRegressor(**best_params)},
        freq="D",
        lags=cfg["lags"],
        lag_transforms=lag_transforms,
        date_features=date_feats,
        num_threads=4,
    )

    # Train trên 100% lịch sử
    fcst.fit(df_long, static_features=[])
    print(f"   ✅ Train hoàn thành: "
          f"{df_long['ds'].min().date()} → {df_long['ds'].max().date()}")

    # Dự báo 548 ngày
    print(f"   ⏳ Đang dự báo {cfg['forecast_horizon']} ngày...")
    forecast_long = fcst.predict(h=cfg["forecast_horizon"])

    # Pivot Long → Wide
    submission = (
        forecast_long
        .pivot(index="ds", columns="unique_id", values="LightGBM")
        .reset_index()
        .rename(columns={"ds": "Date"})
    )
    submission.columns.name = None
    submission = submission[["Date"] + cfg["target_cols"]]
    for col in cfg["target_cols"]:
        submission[col] = submission[col].round(2)

    # Kiểm tra ngày đầu/cuối
    assert str(submission["Date"].min().date()) == cfg["forecast_start"], (
        f"Ngày bắt đầu sai: {submission['Date'].min().date()}"
    )
    assert len(submission) == cfg["forecast_horizon"], (
        f"Số dòng sai: {len(submission)}"
    )

    submission.to_csv(cfg["submission_file"], index=False, date_format="%Y-%m-%d")
    print(f"   ✅ Đã lưu submission → {cfg['submission_file']}")
    print(f"      {len(submission)} dòng | "
          f"{submission['Date'].min().date()} → {submission['Date'].max().date()}")

    # Đánh giá nhanh trên held-out test 30%
    _, df_test, _ = temporal_split(df_long, cfg["train_ratio"])
    eval_fcst = MLForecast(
        models={"LightGBM": lgb.LGBMRegressor(**best_params)},
        freq="D",
        lags=cfg["lags"],
        lag_transforms=lag_transforms,
        date_features=date_feats,
        num_threads=4,
    )
    df_train, _, _ = temporal_split(df_long, cfg["train_ratio"])
    eval_fcst.fit(df_train, static_features=[])
    eval_pred = eval_fcst.predict(h=df_test["ds"].nunique())
    eval_df   = eval_pred.merge(
        df_test[["unique_id", "ds", "y"]], on=["unique_id", "ds"], how="inner"
    )

    print("\n" + "=" * 58)
    print(f"{'📊  KẾT QUẢ TRÊN TẬP TEST (30%) — BEST PARAMS':^58}")
    print("=" * 58)
    print(f"{'Metric':<18} {'Revenue':>19} {'COGS':>19}")
    print("-" * 58)
    for uid in cfg["target_cols"]:
        mask    = eval_df["unique_id"] == uid
        y_true  = eval_df.loc[mask, "y"].values
        y_pred_ = eval_df.loc[mask, "LightGBM"].values
        safe_y  = np.where(np.abs(y_true) < 1e-8, 1e-8, y_true)
        mae_    = mean_absolute_error(y_true, y_pred_)
        rmse_   = np.sqrt(mean_squared_error(y_true, y_pred_))
        mape_   = np.mean(np.abs((y_true - y_pred_) / safe_y)) * 100
        print(f"  {uid}")
        print(f"    MAE    : {mae_:>15,.2f}")
        print(f"    RMSE   : {rmse_:>15,.2f}")
        print(f"    MAPE   : {mape_:>14.2f}%")
    print("=" * 58)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    best_params = run_tuning(TUNING_CFG)
    train_and_submit(best_params, TUNING_CFG)