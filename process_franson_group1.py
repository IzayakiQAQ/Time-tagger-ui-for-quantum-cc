import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd


def load_histogram(hist_path: str) -> pd.DataFrame:
    data = np.loadtxt(hist_path)
    if data.ndim != 2 or data.shape[1] < 2:
        raise ValueError(f"Invalid histogram file: {hist_path}")
    return pd.DataFrame({"delay_ps": data[:, 0], "counts": data[:, 1]})


def find_middle_peak_delay(hist: pd.DataFrame, min_peak_spacing_ps: float = 400.0) -> float:
    delays = hist["delay_ps"].to_numpy(dtype=float)
    counts = hist["counts"].to_numpy(dtype=float)
    peak_candidates = []

    for idx in range(1, len(counts) - 1):
        if counts[idx] >= counts[idx - 1] and counts[idx] >= counts[idx + 1] and counts[idx] > 0:
            peak_candidates.append((counts[idx], delays[idx]))

    if not peak_candidates:
        raise ValueError("No local peaks found in histogram")

    peak_candidates.sort(key=lambda item: item[0], reverse=True)
    selected = []
    for amplitude, delay in peak_candidates:
        if all(abs(delay - kept_delay) >= min_peak_spacing_ps for _, kept_delay in selected):
            selected.append((amplitude, delay))
        if len(selected) >= 3:
            break

    if len(selected) >= 3:
        return float(sorted(delay for _, delay in selected)[1])

    return float(max(peak_candidates, key=lambda item: item[0])[1])


def coincidence_counts_from_link1(hist_path: str, half_window_ps: float = 300.0) -> dict:
    hist = load_histogram(hist_path)
    middle_peak_delay_ps = find_middle_peak_delay(hist)
    mask = (
        (hist["delay_ps"] >= middle_peak_delay_ps - half_window_ps)
        & (hist["delay_ps"] <= middle_peak_delay_ps + half_window_ps)
    )
    coincidence_counts = int(hist.loc[mask, "counts"].sum())
    return {
        "middle_peak_delay_ps": middle_peak_delay_ps,
        "coincidence_counts": coincidence_counts,
    }


def smooth_values(values: np.ndarray, window: int = 5) -> np.ndarray:
    if window <= 1 or len(values) <= 2:
        return values.astype(float, copy=True)
    return (
        pd.Series(values, dtype=float)
        .rolling(window=window, center=True, min_periods=1)
        .mean()
        .to_numpy(dtype=float)
    )


def fill_zero_signs(signs: np.ndarray) -> np.ndarray:
    signs = signs.astype(int, copy=True)
    last_nonzero = 0
    for idx in range(len(signs)):
        if signs[idx] != 0:
            last_nonzero = signs[idx]
        elif last_nonzero != 0:
            signs[idx] = last_nonzero

    last_nonzero = 0
    for idx in range(len(signs) - 1, -1, -1):
        if signs[idx] != 0:
            last_nonzero = signs[idx]
        elif last_nonzero != 0:
            signs[idx] = last_nonzero

    if np.all(signs == 0):
        signs[:] = -1
    return signs


def phase_from_reference(series: pd.Series, vmin: float | None = None, vmax: float | None = None) -> np.ndarray:
    values = series.to_numpy(dtype=float)
    if vmin is None:
        vmin = float(np.min(values))
    if vmax is None:
        vmax = float(np.max(values))
    if math.isclose(vmax, vmin):
        raise ValueError(f"Reference singles are flat: min=max={vmin}")

    normalized = np.clip((values - vmin) / (vmax - vmin), 0.0, 1.0)
    phase_mod = np.arccos(2.0 * normalized - 1.0)  # 0..pi

    smoothed = smooth_values(values, window=5)
    slope_sign = np.sign(np.gradient(smoothed))
    slope_sign = fill_zero_signs(slope_sign)

    branch_phase = np.where(slope_sign <= 0, phase_mod, 2.0 * math.pi - phase_mod)

    unwrapped = [float(branch_phase[0])]
    for idx in range(1, len(branch_phase)):
        prev = unwrapped[-1]
        base = float(branch_phase[idx])
        candidates = [base + 2.0 * math.pi * k for k in range(-3, 4)]
        best = min(candidates, key=lambda value: abs(value - prev))
        unwrapped.append(float(best))
    return np.asarray(unwrapped, dtype=float)


def process_group(
    run_dir: Path,
    group_name: str = "group1",
    half_window_ps: float = 300.0,
    idler_ref_min_khz: float = 0.5,
    idler_ref_max_khz: float = 110.0,
) -> pd.DataFrame:
    manifest_path = run_dir / "manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.csv not found: {manifest_path}")

    df = pd.read_csv(manifest_path)
    df = df[df["group_name"] == group_name].copy()
    if df.empty:
        raise ValueError(f"No {group_name} records found in manifest.csv")

    df = df.sort_values(["step_index", "voltage_set_v"]).reset_index(drop=True)

    coincidence_info = df["link1_hist"].apply(
        lambda path: coincidence_counts_from_link1(path, half_window_ps=half_window_ps)
    )
    coincidence_df = pd.DataFrame(list(coincidence_info))
    df = pd.concat([df, coincidence_df], axis=1)

    phi_signal = phase_from_reference(df["singles_avg_ch1_khz"])
    phi_idler = phase_from_reference(
        df["singles_avg_ch3_khz"],
        vmin=idler_ref_min_khz,
        vmax=idler_ref_max_khz,
    )
    phase_diff = np.unwrap(phi_signal - phi_idler)

    out = pd.DataFrame(
        {
            "group_name": group_name,
            "step_index": df["step_index"].astype(int),
            "voltage_set_v": df["voltage_set_v"].astype(float),
            "signal_ref_ch1_khz": df["singles_avg_ch1_khz"].astype(float),
            "idler_ref_ch3_khz": df["singles_avg_ch3_khz"].astype(float),
            "signal_phase_rad": phi_signal,
            "idler_phase_rad": phi_idler,
            "phase_diff_rad": phase_diff,
            "phase_diff_pi": phase_diff / math.pi,
            "coincidence_counts_link1_pm300ps": df["coincidence_counts"].astype(int),
            "link1_middle_peak_delay_ps": df["middle_peak_delay_ps"].astype(float),
            "link1_hist": df["link1_hist"],
            "link2_hist": df["link2_hist"],
            "singles_csv": df["singles_csv"],
        }
    )

    return out.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process Franson data into phase-difference curve data."
    )
    parser.add_argument(
        "run_dir",
        nargs="?",
        default=r"E:\lzy\测试结果\光源\干涉\run_20260411_162807",
        help="Run directory containing manifest.csv",
    )
    parser.add_argument(
        "--group",
        default="group1",
        choices=["group1", "group2"],
        help="Which group to process.",
    )
    parser.add_argument(
        "--half-window-ps",
        type=float,
        default=300.0,
        help="Half window around the middle Link1 peak for coincidence integration.",
    )
    parser.add_argument(
        "--idler-ref-min-khz",
        type=float,
        default=0.5,
        help="Minimum singles rate for CH3 used to map idler phase.",
    )
    parser.add_argument(
        "--idler-ref-max-khz",
        type=float,
        default=120.0,
        help="Maximum singles rate for CH3 used to map idler phase.",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    result = process_group(
        run_dir,
        group_name=args.group,
        half_window_ps=args.half_window_ps,
        idler_ref_min_khz=args.idler_ref_min_khz,
        idler_ref_max_khz=args.idler_ref_max_khz,
    )

    output_path = run_dir / f"{args.group}_franson_curve.csv"
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Saved: {output_path}")
    print(result.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
