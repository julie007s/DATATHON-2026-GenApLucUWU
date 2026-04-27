from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEATURE_TABLE = ROOT / "data/output/featured_table.parquet"
DEFAULT_BASE_ANALYSIS = ROOT / "data/output/analysis_validated_core_business.csv"
DEFAULT_OUTPUT_DIR = ROOT / "data/output"
DEFAULT_REPORT_DIR = ROOT / "reports/recovery_aware"


@dataclass(frozen=True)
class Candidate:
    name: str
    approach: str
    revenue_factor: np.ndarray
    cogs_factor: np.ndarray
    rationale: str


def _safe_cagr(start_value: float, end_value: float, periods: float) -> float:
    if start_value <= 0 or end_value <= 0 or periods <= 0:
        return 0.0
    return float((end_value / start_value) ** (1.0 / periods) - 1.0)


def _load_inputs(feature_table: Path, base_analysis: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not feature_table.exists():
        raise FileNotFoundError(f"Feature table not found: {feature_table}")
    if not base_analysis.exists():
        raise FileNotFoundError(f"Base analysis not found: {base_analysis}. Run validated core-business pipeline first.")
    history = pd.read_parquet(feature_table, engine="pyarrow")
    history["Date"] = pd.to_datetime(history["Date"])
    history = history.sort_values("Date").reset_index(drop=True)
    forecast = pd.read_csv(base_analysis)
    forecast["Date"] = pd.to_datetime(forecast["Date"])
    return history, forecast


def analyze_regimes(history: pd.DataFrame) -> dict[str, float | str]:
    yearly = history.assign(year=history["Date"].dt.year).groupby("year", as_index=False).agg(
        revenue_mean=("Revenue", "mean"),
        revenue_sum=("Revenue", "sum"),
        cogs_mean=("COGS", "mean"),
        cogs_sum=("COGS", "sum"),
    )
    pre = yearly[yearly["year"] <= 2018]
    shock = yearly[(yearly["year"] >= 2019) & (yearly["year"] <= 2022)]
    if pre.empty or shock.empty:
        raise ValueError("Not enough history to analyze pre-2019 and 2019-2022 regimes.")

    pre_start = float(pre.iloc[0]["revenue_mean"])
    pre_end = float(pre.iloc[-1]["revenue_mean"])
    pre_years = float(pre.iloc[-1]["year"] - pre.iloc[0]["year"])
    pre_cagr = _safe_cagr(pre_start, pre_end, pre_years)
    normal_2018 = pre_end
    shock_mean = float(shock["revenue_mean"].mean())
    gap_ratio = float(np.clip((normal_2018 - shock_mean) / max(normal_2018, 1.0), -0.5, 0.5))

    return {
        "pre_period": f"{int(pre['year'].min())}-{int(pre['year'].max())}",
        "shock_period": f"{int(shock['year'].min())}-{int(shock['year'].max())}",
        "pre_revenue_mean_start": pre_start,
        "pre_revenue_mean_end": pre_end,
        "pre_cagr_daily_mean": pre_cagr,
        "shock_revenue_mean": shock_mean,
        "pandemic_gap_ratio_vs_2018": gap_ratio,
        "yearly_table": yearly.to_dict(orient="records"),
    }


def _linear_factor(n: int, start: float, end: float) -> np.ndarray:
    return np.linspace(start, end, n, dtype=float) if n > 1 else np.asarray([end], dtype=float)


def build_candidates(forecast: pd.DataFrame, regime: dict[str, float | str]) -> list[Candidate]:
    n = len(forecast)
    dates = forecast["Date"]
    horizon_years = (dates - dates.min()).dt.days.to_numpy(dtype=float) / 365.25
    pre_cagr = float(regime["pre_cagr_daily_mean"])
    gap_ratio = float(regime["pandemic_gap_ratio_vs_2018"])
    # Keep all factors bounded and defensible. These are candidate scenarios, not leaderboard-derived multipliers.
    trend_growth = np.clip((1.0 + pre_cagr) ** horizon_years, 0.92, 1.18)
    gap_base = float(np.clip(gap_ratio, 0.0, 0.30))

    candidates: list[Candidate] = []

    # Approach 1: Pre-pandemic trend re-anchoring.
    for label, strength in [("mild", 0.35), ("base", 0.55), ("strong", 0.75)]:
        factor = np.clip(1.0 + (trend_growth - 1.0) * strength + gap_base * strength * 0.20, 0.90, 1.18)
        candidates.append(
            Candidate(
                name=f"recovery_trend_anchor_{label}",
                approach="pre_pandemic_trend_anchor",
                revenue_factor=factor,
                cogs_factor=np.ones(n),
                rationale=(
                    "Re-anchors the validated forecast toward the stable pre-2019 growth trend. "
                    "The factor is bounded and derived from historical pre-shock CAGR."
                ),
            )
        )

    # Approach 2: Regime-weighted proxy. True retraining would be separate; this approximates reduced shock-period drag.
    for label, uplift, cogs_adj in [("core", 0.045, 1.00), ("core_uplift", 0.075, 1.01)]:
        factor = np.clip(1.0 + uplift * _linear_factor(n, 0.8, 1.2), 0.90, 1.12)
        candidates.append(
            Candidate(
                name=f"regime_weighted_{label}",
                approach="regime_weighted_proxy",
                revenue_factor=factor,
                cogs_factor=np.full(n, cogs_adj),
                rationale=(
                    "Proxy for retraining with lower shock-period influence and higher normal-growth influence. "
                    "It tests the expected level effect before implementing full weighted retraining."
                ),
            )
        )

    # Approach 3: Recovery curve.
    for label, start, end in [("mild", 1.02, 1.07), ("base", 1.04, 1.11), ("strong", 1.06, 1.15)]:
        factor = _linear_factor(n, start, end)
        candidates.append(
            Candidate(
                name=f"recovery_curve_{label}",
                approach="recovery_curve",
                revenue_factor=factor,
                cogs_factor=np.ones(n),
                rationale=(
                    "Applies a gradual 2023-2024 recovery path, representing demand normalization after the shock period."
                ),
            )
        )

    return candidates


def _apply_candidate(base: pd.DataFrame, candidate: Candidate) -> pd.DataFrame:
    out = base.copy()
    out["Recovery_Revenue_Factor"] = candidate.revenue_factor
    out["Recovery_COGS_Factor"] = candidate.cogs_factor
    out["Revenue_Base"] = out["Revenue"].astype(float)
    out["COGS_Base"] = out["COGS"].astype(float)
    out["Revenue"] = np.maximum(out["Revenue_Base"] * candidate.revenue_factor, 0)
    out["COGS"] = np.maximum(out["COGS_Base"] * candidate.revenue_factor * candidate.cogs_factor, 0)
    out["Profit"] = out["Revenue"] - out["COGS"]
    out["Approach"] = candidate.approach
    out["Candidate"] = candidate.name
    return out


def _write_regime_markdown(report_dir: Path, regime: dict[str, float | str], summary: pd.DataFrame) -> None:
    lines = [
        "# Recovery Regime Analysis",
        "",
        "## Regime hypothesis",
        "",
        "- Pre-2019: stable normal-growth regime.",
        "- 2019-2022: shock/depressed demand regime.",
        "- 2023-2024: recovery/rebound regime.",
        "",
        "## Estimated historical signals",
        "",
        f"- Pre period: `{regime['pre_period']}`",
        f"- Shock period: `{regime['shock_period']}`",
        f"- Pre-period daily mean CAGR: `{float(regime['pre_cagr_daily_mean']):.4%}`",
        f"- Pandemic gap ratio vs 2018 daily mean: `{float(regime['pandemic_gap_ratio_vs_2018']):.4%}`",
        "",
        "## Generated candidate groups",
        "",
        "| Approach | What it tests |",
        "|---|---|",
        "| `pre_pandemic_trend_anchor` | Re-anchor forecast toward pre-shock growth trend |",
        "| `regime_weighted_proxy` | Approximate reduced shock-period training influence |",
        "| `recovery_curve` | Gradual 2023-2024 demand normalization curve |",
        "| `recovery_selection` | Select a defensible candidate from recovery-aware scenarios |",
        "",
        "## Candidate summary",
        "",
        summary.to_markdown(index=False),
        "",
        "## Guardrail",
        "",
        "These factors are bounded and derived from the regime hypothesis. They should be validated/stress-tested before final selection.",
    ]
    (report_dir / "recovery_regime_analysis.md").write_text("\n".join(lines), encoding="utf-8")


def generate_recovery_candidates(feature_table: Path, base_analysis: Path, output_dir: Path, report_dir: Path) -> pd.DataFrame:
    history, base = _load_inputs(feature_table, base_analysis)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    regime = analyze_regimes(history)
    candidates = build_candidates(base, regime)
    rows = []
    generated = {}
    for candidate in candidates:
        out = _apply_candidate(base, candidate)
        submission = output_dir / f"submission_{candidate.name}.csv"
        analysis = output_dir / f"analysis_{candidate.name}.csv"
        out[["Date", "Revenue", "COGS"]].to_csv(submission, index=False)
        out.to_csv(analysis, index=False)
        generated[candidate.name] = out
        rows.append(
            {
                "candidate": candidate.name,
                "approach": candidate.approach,
                "submission": submission.name,
                "analysis": analysis.name,
                "revenue_factor_start": float(candidate.revenue_factor[0]),
                "revenue_factor_end": float(candidate.revenue_factor[-1]),
                "revenue_factor_mean": float(np.mean(candidate.revenue_factor)),
                "cogs_factor_mean": float(np.mean(candidate.cogs_factor)),
                "revenue_mean": float(out["Revenue"].mean()),
                "cogs_mean": float(out["COGS"].mean()),
                "profit_mean": float(out["Profit"].mean()),
                "rationale": candidate.rationale,
            }
        )

    summary = pd.DataFrame(rows)
    summary.to_csv(report_dir / "recovery_candidate_summary.csv", index=False)

    # Approach 4: selection. Choose the base recovery curve as the default defensible scenario:
    # it is transparent, bounded, and directly maps to the user's 2023-2024 recovery hypothesis.
    selected_name = "recovery_curve_base"
    selected = generated[selected_name]
    selected[["Date", "Revenue", "COGS"]].to_csv(output_dir / "submission_recovery_selected.csv", index=False)
    selected.to_csv(output_dir / "analysis_recovery_selected.csv", index=False)

    selection = {
        "selected_candidate": selected_name,
        "selected_submission": "submission_recovery_selected.csv",
        "selection_reason": (
            "Default selection uses the base recovery curve because it directly represents gradual 2023-2024 demand recovery, "
            "keeps the validated core-business shape, and avoids relying on public leaderboard-derived multipliers."
        ),
        "regime": {k: v for k, v in regime.items() if k != "yearly_table"},
    }
    (report_dir / "recovery_model_selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
    (report_dir / "recovery_model_selection.md").write_text(
        "# Recovery Model Selection\n\n"
        f"Selected candidate: `{selected_name}`\n\n"
        "Selected submission:\n\n"
        "```text\n"
        "data/output/submission_recovery_selected.csv\n"
        "```\n\n"
        "## Reason\n\n"
        f"{selection['selection_reason']}\n",
        encoding="utf-8",
    )
    _write_regime_markdown(report_dir, regime, summary)
    (report_dir / "recovery_regime_metadata.json").write_text(json.dumps(regime, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate recovery-aware forecast candidates from validated core-business forecast.")
    parser.add_argument("--feature-table", type=Path, default=DEFAULT_FEATURE_TABLE)
    parser.add_argument("--base-analysis", type=Path, default=DEFAULT_BASE_ANALYSIS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()

    summary = generate_recovery_candidates(args.feature_table, args.base_analysis, args.output_dir, args.report_dir)
    print(f"Saved recovery-aware reports -> {args.report_dir}")
    print(summary[["candidate", "approach", "submission", "revenue_factor_mean", "revenue_mean", "cogs_mean"]].to_string(index=False))


if __name__ == "__main__":
    main()
