from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.inspection import PartialDependenceDisplay, permutation_importance

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.feature_contract import get_model_feature_columns  # noqa: E402
from src.logger import logger  # noqa: E402

sns.set_theme(style="whitegrid", font="DejaVu Sans")


FEATURE_BUSINESS_RULES = [
    (r"lag|rolling|roll|ma|season|year_ago", "nhu cầu lịch sử và tính mùa vụ"),
    (r"stock|inventory|stockout|supply|reorder|fill_rate|sell_through", "khả năng đáp ứng hàng tồn kho và rủi ro hết hàng"),
    (r"promotion|promo|discount|coupon|campaign", "tác động khuyến mãi và kích cầu"),
    (r"rating|review|sentiment", "chất lượng trải nghiệm và mức độ hài lòng khách hàng"),
    (r"traffic|session|visitor|click|view", "ý định mua hàng và lưu lượng truy cập"),
    (r"month|week|day|holiday|quarter|dow|weekday", "hiệu ứng lịch, mùa vụ ngắn hạn và ngày đặc biệt"),
    (r"price|cost|margin|cogs|profit", "giá bán, chi phí và biên lợi nhuận"),
    (r"category|segment|product", "cơ cấu danh mục sản phẩm"),
    (r"customer|cohort|retention", "cấu trúc khách hàng và khả năng mua lại"),
]


def _business_meaning(feature: str) -> str:
    normalized = feature.lower()
    for pattern, meaning in FEATURE_BUSINESS_RULES:
        if re.search(pattern, normalized):
            return meaning
    return "tín hiệu vận hành/tổng hợp khác mà mô hình thấy có liên quan đến doanh thu"


def _load_feature_table(feature_table_path: Path, sample_rows: int | None) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    df = pd.read_parquet(feature_table_path, engine="pyarrow")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    features = get_model_feature_columns(df)
    if sample_rows:
        df = df.tail(sample_rows).copy().reset_index(drop=True)
        logger.info(f"  Explainability sample: last {len(df)} rows")
    X = df[features].fillna(0)
    return df, X, features


def _load_models(model_dir: Path, model_arch: str) -> dict[str, object]:
    if model_arch == "seasonal_xgb_ratio":
        paths = {
            "Revenue_Residual": model_dir / "seasonal_xgb_revenue_residual.joblib",
            "COGS_Ratio": model_dir / "seasonal_xgb_cogs_ratio.joblib",
        }
    elif model_arch == "arima_hybrid":
        paths = {
            "Revenue_Residual": model_dir / "xgboost_revenue_residual.joblib",
            "COGS_Residual": model_dir / "xgboost_cogs_residual.joblib",
        }
    else:
        raise ValueError(f"Unsupported model_arch: {model_arch}")

    models = {}
    for name, path in paths.items():
        if path.exists():
            models[name] = joblib.load(path)
            logger.info(f"  Loaded {name}: {path}")
        else:
            logger.warning(f"  Missing model artifact for {name}: {path}")
    if not models:
        raise FileNotFoundError(f"No explainable XGBoost model artifacts found in {model_dir}")
    return models


def _booster_importance(model, features: list[str], importance_type: str) -> pd.DataFrame:
    booster = model.get_booster()
    raw = booster.get_score(importance_type=importance_type)
    rows = []
    for idx, feature in enumerate(features):
        rows.append({"Feature": feature, "Importance": float(raw.get(feature, raw.get(f"f{idx}", 0.0)))})
    return pd.DataFrame(rows).sort_values("Importance", ascending=False)


def _xgb_contrib_importance(model, X: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    booster = model.get_booster()
    contrib = booster.predict(xgb_dmatrix(X, features), pred_contribs=True)
    # Last column is bias term. Mean absolute contribution approximates global TreeSHAP importance.
    values = np.abs(contrib[:, :-1]).mean(axis=0)
    return pd.DataFrame({"Feature": features, "Importance": values}).sort_values("Importance", ascending=False)


def xgb_dmatrix(X: pd.DataFrame, features: list[str]):
    import xgboost as xgb

    return xgb.DMatrix(X[features], feature_names=features)


def _plot_bar(df: pd.DataFrame, path: Path, title: str, top_n: int) -> None:
    plot_df = df.head(top_n).sort_values("Importance", ascending=True)
    plt.figure(figsize=(11, max(5, 0.33 * len(plot_df))))
    sns.barplot(data=plot_df, x="Importance", y="Feature", hue="Feature", palette="mako", legend=False)
    plt.title(title)
    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=180)
    plt.close()


def _safe_permutation_importance(model, X: pd.DataFrame, y_proxy: np.ndarray, features: list[str], top_n: int) -> pd.DataFrame:
    try:
        result = permutation_importance(model, X[features], y_proxy, n_repeats=5, random_state=42, n_jobs=-1, scoring="neg_mean_absolute_error")
        df = pd.DataFrame({"Feature": features, "Importance": result.importances_mean})
        return df.sort_values("Importance", ascending=False)
    except Exception as exc:
        logger.warning(f"  Permutation importance failed: {exc}")
        return pd.DataFrame({"Feature": features, "Importance": np.zeros(len(features))}).sort_values("Importance", ascending=False)


def _plot_pdp(model, X: pd.DataFrame, feature_names: list[str], features_to_plot: list[str], output_dir: Path, target_key: str) -> list[Path]:
    paths = []
    for feature in features_to_plot:
        if feature not in X.columns or X[feature].nunique(dropna=True) < 2:
            continue
        try:
            fig, ax = plt.subplots(figsize=(8, 5))
            X_pdp = X[feature_names].astype(float)
            PartialDependenceDisplay.from_estimator(model, X_pdp, [feature], ax=ax, grid_resolution=25)
            ax.set_title(f"PDP - {target_key} - {feature}")
            plt.tight_layout()
            path = output_dir / f"partial_dependence_{target_key}_{feature}.png"
            plt.savefig(path, dpi=180)
            plt.close(fig)
            paths.append(path)
        except Exception as exc:
            logger.warning(f"  PDP skipped for {target_key}/{feature}: {exc}")
    return paths


def _write_business_report(report_path: Path, model_arch: str, all_importance: pd.DataFrame, top_n: int, pdp_top_n: int) -> None:
    lines = [
        f"# Business Explainability Report - `{model_arch}`",
        "",
        "Báo cáo này diễn giải các tín hiệu quan trọng mà mô hình XGBoost học được theo ngôn ngữ kinh doanh.",
        "",
        "## Cách đọc",
        "",
        "- `gain`: feature giúp giảm lỗi nhiều trong cây quyết định.",
        "- `xgb_contrib`: đóng góp tuyệt đối trung bình kiểu TreeSHAP native của XGBoost.",
        "- `permutation`: mức độ lỗi tăng khi xáo trộn feature.",
        f"- PDP chỉ vẽ cho Top {pdp_top_n} feature để tránh chi phí tính toán quá lớn.",
        "",
        "## Các yếu tố dẫn động chính",
        "",
    ]
    top = all_importance.sort_values("CompositeImportance", ascending=False).head(top_n)
    for _, row in top.iterrows():
        feature = row["Feature"]
        target = row["Target"]
        meaning = _business_meaning(feature)
        lines.append(
            f"- **{feature}** trong mô hình **{target}** là tín hiệu về **{meaning}**. "
            f"Mức quan trọng tổng hợp: `{row['CompositeImportance']:.6g}`. "
            "Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline."
        )
    lines.extend([
        "",
        "## Gợi ý chọn/xóa feature",
        "",
        "- Ưu tiên giữ feature có thứ hạng cao ở cả `gain`, `xgb_contrib` và `permutation`.",
        "- Cân nhắc xóa feature có importance gần 0 ở tất cả phương pháp, nhất là nếu khó giải thích về mặt kinh doanh.",
        "- Với feature tương quan cao cùng nhóm, chỉ giữ biến dễ giải thích và ổn định nhất.",
        "- Không xóa feature chỉ vì PDP không được vẽ; PDP mặc định chỉ chạy trên Top N để tiết kiệm thời gian.",
    ])
    report_path.write_text("\n".join(lines), encoding="utf-8")


def explain_models(
    feature_table_path: Path,
    model_dir: Path,
    report_dir: Path,
    model_arch: str,
    sample_rows: int | None,
    top_n: int,
    pdp_top_n: int,
) -> None:
    df, X, features = _load_feature_table(feature_table_path, sample_rows)
    models = _load_models(model_dir, model_arch)
    output_dir = report_dir / "explainability" / model_arch
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for target_key, model in models.items():
        target_dir = output_dir / target_key
        target_dir.mkdir(parents=True, exist_ok=True)
        y_proxy = model.predict(X[features])

        gain_df = _booster_importance(model, features, "gain")
        weight_df = _booster_importance(model, features, "weight")
        cover_df = _booster_importance(model, features, "cover")
        contrib_df = _xgb_contrib_importance(model, X, features)
        perm_df = _safe_permutation_importance(model, X, y_proxy, features, top_n)

        gain_df.to_csv(target_dir / "feature_importance_gain.csv", index=False)
        weight_df.to_csv(target_dir / "feature_importance_weight.csv", index=False)
        cover_df.to_csv(target_dir / "feature_importance_cover.csv", index=False)
        contrib_df.to_csv(target_dir / "xgb_contrib_importance.csv", index=False)
        perm_df.to_csv(target_dir / "permutation_importance.csv", index=False)

        _plot_bar(gain_df, target_dir / f"feature_importance_gain_top{top_n}.png", f"{target_key}: XGBoost Gain Importance", top_n)
        _plot_bar(contrib_df, target_dir / f"xgb_contrib_importance_top{top_n}.png", f"{target_key}: Native TreeSHAP Contribution", top_n)
        _plot_bar(perm_df, target_dir / f"permutation_importance_top{top_n}.png", f"{target_key}: Permutation Importance", top_n)

        merged = pd.DataFrame({"Feature": features})
        for name, src in [("Gain", gain_df), ("Weight", weight_df), ("Cover", cover_df), ("XGBContribution", contrib_df), ("Permutation", perm_df)]:
            merged = merged.merge(src.rename(columns={"Importance": name}), on="Feature", how="left")
        merged = merged.fillna(0)
        merged["Target"] = target_key
        scale_cols = ["Gain", "Weight", "Cover", "XGBContribution", "Permutation"]
        normalized = []
        for col in scale_cols:
            denom = merged[col].abs().max()
            normalized.append(merged[col].abs() / denom if denom else merged[col].abs())
        merged["CompositeImportance"] = np.vstack(normalized).mean(axis=0)
        merged = merged.sort_values("CompositeImportance", ascending=False)
        merged["BusinessMeaning"] = merged["Feature"].map(_business_meaning)
        merged.to_csv(target_dir / "feature_recommendations.csv", index=False)
        all_rows.append(merged)

        if pdp_top_n > 0:
            pdp_features = contrib_df.head(pdp_top_n)["Feature"].tolist()
            _plot_pdp(model, X, features, pdp_features, target_dir, target_key)

    all_importance = pd.concat(all_rows, ignore_index=True).sort_values("CompositeImportance", ascending=False)
    all_importance.to_csv(output_dir / "all_feature_importances.csv", index=False)
    _write_business_report(output_dir / "business_explanation.md", model_arch, all_importance, top_n, pdp_top_n)
    logger.info(f"  Explainability report saved to: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate XGBoost explainability tables, charts, PDPs, and business explanation.")
    parser.add_argument("--feature-table", type=Path, default=PROJECT_ROOT / "data/output/featured_table.parquet")
    parser.add_argument("--model-dir", type=Path, default=PROJECT_ROOT / "models")
    parser.add_argument("--report-dir", type=Path, default=PROJECT_ROOT / "reports")
    parser.add_argument("--model_arch", choices=["arima_hybrid", "seasonal_xgb_ratio"], default="seasonal_xgb_ratio")
    parser.add_argument("--sample-rows", type=int, default=1500)
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--pdp-top-n", type=int, default=10, help="Set 0 to disable PDP. Defaults to Top 10 features only.")
    args = parser.parse_args()

    explain_models(
        feature_table_path=args.feature_table,
        model_dir=args.model_dir,
        report_dir=args.report_dir,
        model_arch=args.model_arch,
        sample_rows=args.sample_rows,
        top_n=args.top_n,
        pdp_top_n=args.pdp_top_n,
    )


if __name__ == "__main__":
    main()
