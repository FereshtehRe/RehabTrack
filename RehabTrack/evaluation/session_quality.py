from pathlib import Path
import argparse
import json
import math

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "raw" / "rehab001"
OUTPUT_FILE = BASE_DIR / "data" / "session_quality.json"

REQUIRED_COLUMNS = [
    "device_ms",
    "seq",
    "gx_dps",
    "gy_dps",
    "gz_dps",
]

CALIBRATION_SECONDS = 5.0

# These are only sanity limits, NOT repetition thresholds.
MAX_REASONABLE_GYRO_DPS = 1500.0
LARGE_GAP_FACTOR = 3.0


def latest_csv():
    files = list(DATA_DIR.glob("*.csv"))

    if not files:
        raise FileNotFoundError(
            f"No CSV files found in {DATA_DIR}"
        )

    return max(
        files,
        key=lambda p: p.stat().st_mtime
    )


def safe_float(value, default=0.0):
    try:
        value = float(value)

        if math.isfinite(value):
            return value

    except Exception:
        pass

    return default


def analyze_quality(path):
    result = {
        "file": path.name,
        "path": str(path),
        "status": "unknown",
        "issues": [],
        "warnings": [],
        "metrics": {},
    }

    try:
        df = pd.read_csv(path)

    except pd.errors.EmptyDataError:
        result["status"] = "fail"
        result["issues"].append(
            "CSV file is empty."
        )
        return result

    except Exception as exc:
        result["status"] = "fail"
        result["issues"].append(
            f"Could not read CSV: {exc}"
        )
        return result


    # --------------------------------------------------
    # Required columns
    # --------------------------------------------------

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:
        result["status"] = "fail"
        result["issues"].append(
            "Missing required columns: "
            + ", ".join(missing)
        )
        return result


    sample_count = len(df)

    result["metrics"]["samples"] = sample_count

    if sample_count < 2:
        result["status"] = "fail"
        result["issues"].append(
            "Recording contains fewer than 2 samples."
        )
        return result


    # --------------------------------------------------
    # Device time
    # --------------------------------------------------

    device_ms = pd.to_numeric(
        df["device_ms"],
        errors="coerce"
    ).to_numpy(dtype=float)

    finite_time = np.isfinite(device_ms)

    invalid_time_count = int(
        np.sum(~finite_time)
    )

    result["metrics"]["invalid_time_samples"] = (
        invalid_time_count
    )

    if invalid_time_count:
        result["issues"].append(
            f"{invalid_time_count} samples have invalid device time."
        )


    valid_times = device_ms[finite_time]

    if len(valid_times) >= 2:

        duration_seconds = max(
            0.0,
            (
                valid_times[-1]
                - valid_times[0]
            ) / 1000.0
        )

        diffs_ms = np.diff(valid_times)

        positive_diffs = diffs_ms[
            diffs_ms > 0
        ]

    else:
        duration_seconds = 0.0
        positive_diffs = np.array([])


    result["metrics"]["duration_seconds"] = round(
        duration_seconds,
        2
    )


    # --------------------------------------------------
    # Sampling rate
    # --------------------------------------------------

    if len(positive_diffs):

        median_interval_ms = float(
            np.median(positive_diffs)
        )

        sample_rate = (
            1000.0 / median_interval_ms
            if median_interval_ms > 0
            else 0.0
        )

        result["metrics"]["sample_rate_hz"] = round(
            sample_rate,
            2
        )

        result["metrics"]["median_interval_ms"] = round(
            median_interval_ms,
            2
        )


        large_gap_limit = (
            median_interval_ms
            * LARGE_GAP_FACTOR
        )

        large_gaps = positive_diffs[
            positive_diffs
            > large_gap_limit
        ]

        result["metrics"]["large_time_gaps"] = int(
            len(large_gaps)
        )

        if len(large_gaps):
            result["warnings"].append(
                f"{len(large_gaps)} unusually large sampling gaps detected."
            )

    else:

        sample_rate = 0.0

        result["metrics"]["sample_rate_hz"] = 0.0
        result["metrics"]["median_interval_ms"] = 0.0
        result["metrics"]["large_time_gaps"] = 0


    # --------------------------------------------------
    # Calibration window
    # --------------------------------------------------

    if duration_seconds < CALIBRATION_SECONDS:

        result["issues"].append(
            "Recording is shorter than the 5 second "
            "sensor calibration period."
        )

        result["metrics"]["calibration_available"] = False

    else:

        result["metrics"]["calibration_available"] = True


    # --------------------------------------------------
    # Gyroscope quality
    # --------------------------------------------------

    gyro_columns = [
        "gx_dps",
        "gy_dps",
        "gz_dps",
    ]

    total_invalid_gyro = 0
    max_abs_gyro = 0.0

    for column in gyro_columns:

        values = pd.to_numeric(
            df[column],
            errors="coerce"
        ).to_numpy(dtype=float)

        finite = np.isfinite(values)

        invalid = int(
            np.sum(~finite)
        )

        total_invalid_gyro += invalid

        finite_values = values[finite]

        if len(finite_values):

            axis_max = float(
                np.max(
                    np.abs(
                        finite_values
                    )
                )
            )

            max_abs_gyro = max(
                max_abs_gyro,
                axis_max
            )


    result["metrics"]["invalid_gyro_samples"] = (
        total_invalid_gyro
    )

    result["metrics"]["peak_absolute_gyro_dps"] = round(
        max_abs_gyro,
        2
    )


    if total_invalid_gyro:
        result["issues"].append(
            f"{total_invalid_gyro} invalid gyro values detected."
        )


    if max_abs_gyro > MAX_REASONABLE_GYRO_DPS:

        result["warnings"].append(
            "Very large gyro value detected "
            f"({max_abs_gyro:.1f} °/s). "
            "Check sensor mounting or motion spikes."
        )


    # --------------------------------------------------
    # Sequence continuity
    # --------------------------------------------------

    seq = pd.to_numeric(
        df["seq"],
        errors="coerce"
    ).to_numpy(dtype=float)

    seq = seq[np.isfinite(seq)]

    estimated_missing_packets = 0

    if len(seq) >= 2:

        seq_diff = np.diff(seq)

        for diff in seq_diff:
            if diff > 1:
                estimated_missing_packets += int(
                    diff - 1
                )


    result["metrics"][
        "estimated_missing_packets"
    ] = estimated_missing_packets


    if estimated_missing_packets:
        result["warnings"].append(
            f"Approximately {estimated_missing_packets} "
            "BLE packets may be missing."
        )


    # --------------------------------------------------
    # General duration guidance
    # --------------------------------------------------

    movement_seconds = max(
        0.0,
        duration_seconds
        - CALIBRATION_SECONDS
    )

    result["metrics"]["usable_movement_seconds"] = round(
        movement_seconds,
        2
    )


    if (
        duration_seconds >= CALIBRATION_SECONDS
        and movement_seconds < 2.0
    ):
        result["warnings"].append(
            "Very little movement time remains after calibration."
        )


    # --------------------------------------------------
    # Final status
    # --------------------------------------------------

    if result["issues"]:
        result["status"] = "fail"

    elif result["warnings"]:
        result["status"] = "warning"

    else:
        result["status"] = "good"


    return result


def save_result(result):
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            result,
            indent=2
        )
    )


def print_report(result):
    print()
    print("========================================")
    print(" RehabTrack session quality")
    print("========================================")

    print("File:", result["file"])
    print(
        "Status:",
        result["status"].upper()
    )

    print()

    for key, value in result["metrics"].items():
        label = key.replace(
            "_",
            " "
        ).capitalize()

        print(
            f"{label}: {value}"
        )


    if result["issues"]:
        print()
        print("ISSUES")

        for issue in result["issues"]:
            print(
                "✗",
                issue
            )


    if result["warnings"]:
        print()
        print("WARNINGS")

        for warning in result["warnings"]:
            print(
                "!",
                warning
            )


    if (
        not result["issues"]
        and not result["warnings"]
    ):
        print()
        print(
            "✓ No obvious recording-quality problems detected."
        )


    print()
    print(
        "Note: this checks sensor/data quality only."
    )

    print(
        "It does not determine whether a rehabilitation "
        "movement was performed correctly."
    )

    print("========================================")
    print()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "file",
        nargs="?",
        help="CSV session filename or path. "
             "Defaults to latest recording."
    )

    args = parser.parse_args()


    if args.file:

        path = Path(args.file)

        if not path.exists():
            path = DATA_DIR / args.file

    else:
        path = latest_csv()


    if not path.exists():
        raise SystemExit(
            f"File not found: {path}"
        )


    result = analyze_quality(path)

    save_result(result)
    print_report(result)


    if result["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
