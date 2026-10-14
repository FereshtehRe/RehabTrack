from pathlib import Path
import json
import statistics
import sys


BASE_DIR = Path(__file__).resolve().parents[1]
GATEWAY_DIR = BASE_DIR / "gateway"
DATA_DIR = BASE_DIR / "data" / "raw" / "rehab001"

LABEL_FILE = (
    BASE_DIR
    / "data"
    / "session_labels.json"
)

REPORT_FILE = (
    BASE_DIR
    / "data"
    / "algorithm_evaluation.json"
)

sys.path.insert(
    0,
    str(GATEWAY_DIR)
)

import app as rehab_app


def load_labels():
    if not LABEL_FILE.exists():
        return {}

    try:
        return json.loads(
            LABEL_FILE.read_text()
        )
    except Exception as exc:
        raise SystemExit(
            f"Could not read labels: {exc}"
        )


def detected_reps(filename):
    try:
        result = rehab_app.analyze_session(
            filename
        )

        if not result:
            return 0

        return int(
            result.get(
                "repetitions",
                0
            )
            or 0
        )

    except Exception as exc:
        print(
            f"! Analysis failed for "
            f"{filename}: {exc}"
        )

        return None


def summarize(rows):
    valid = [
        row
        for row in rows
        if row["detected_reps"]
        is not None
    ]

    if not valid:
        return {
            "sessions": 0,
            "mean_absolute_error": None,
            "exact_accuracy_percent": None,
            "within_one_rep_percent": None,
            "mean_signed_error": None,
        }

    absolute_errors = [
        row["absolute_error"]
        for row in valid
    ]

    signed_errors = [
        row["signed_error"]
        for row in valid
    ]

    exact = sum(
        1
        for row in valid
        if row["absolute_error"] == 0
    )

    within_one = sum(
        1
        for row in valid
        if row["absolute_error"] <= 1
    )

    count = len(valid)

    return {
        "sessions": count,

        "mean_absolute_error":
            round(
                statistics.mean(
                    absolute_errors
                ),
                2
            ),

        "mean_signed_error":
            round(
                statistics.mean(
                    signed_errors
                ),
                2
            ),

        "exact_accuracy_percent":
            round(
                100 * exact / count,
                1
            ),

        "within_one_rep_percent":
            round(
                100 * within_one / count,
                1
            ),
    }


def main():
    labels = load_labels()

    if not labels:
        print()
        print(
            "No ground-truth sessions "
            "have been labelled yet."
        )
        print()
        print(
            "Example:"
        )
        print(
            "make label "
            "FILE=knee_extension_2026-10-14_00-15-44.csv "
            "REPS=10"
        )
        print()
        return


    rows = []

    for filename, label in labels.items():

        csv_path = DATA_DIR / filename

        if not csv_path.exists():
            print(
                f"! Missing CSV: {filename}"
            )
            continue


        expected = int(
            label.get(
                "expected_reps",
                0
            )
        )

        exercise = label.get(
            "exercise",
            "unknown"
        )

        detected = detected_reps(
            filename
        )


        if detected is None:
            signed_error = None
            absolute_error = None

        else:
            signed_error = (
                detected - expected
            )

            absolute_error = abs(
                signed_error
            )


        rows.append({
            "file": filename,
            "exercise": exercise,
            "expected_reps": expected,
            "detected_reps": detected,
            "signed_error": signed_error,
            "absolute_error":
                absolute_error
        })


    knee_rows = [
        row
        for row in rows
        if row["exercise"]
        == "knee_extension"
    ]

    squat_rows = [
        row
        for row in rows
        if row["exercise"]
        == "squat"
    ]


    report = {
        "overall":
            summarize(rows),

        "knee_extension":
            summarize(knee_rows),

        "squat":
            summarize(squat_rows),

        "sessions":
            rows
    }


    REPORT_FILE.write_text(
        json.dumps(
            report,
            indent=2
        )
    )


    print()
    print(
        "=============================================="
    )
    print(
        " RehabTrack repetition algorithm evaluation"
    )
    print(
        "=============================================="
    )

    print()

    for row in rows:

        detected = row[
            "detected_reps"
        ]

        expected = row[
            "expected_reps"
        ]

        error = row[
            "signed_error"
        ]

        print(
            row["file"]
        )

        print(
            f"  expected: {expected}"
        )

        print(
            f"  detected: {detected}"
        )

        if error is not None:

            sign = (
                "+"
                if error > 0
                else ""
            )

            print(
                f"  error:    "
                f"{sign}{error}"
            )

        print()


    overall = report["overall"]

    print(
        "----------------------------------------------"
    )

    print(
        "OVERALL"
    )

    print(
        "Sessions:",
        overall["sessions"]
    )

    print(
        "Mean absolute error:",
        overall[
            "mean_absolute_error"
        ]
    )

    print(
        "Exact match:",
        str(
            overall[
                "exact_accuracy_percent"
            ]
        ) + "%"
    )

    print(
        "Within ±1 rep:",
        str(
            overall[
                "within_one_rep_percent"
            ]
        ) + "%"
    )

    print(
        "Mean signed error:",
        overall[
            "mean_signed_error"
        ]
    )


    for exercise, title in [
        (
            "knee_extension",
            "KNEE EXTENSION"
        ),
        (
            "squat",
            "SQUAT"
        )
    ]:

        result = report[exercise]

        if result["sessions"] == 0:
            continue

        print()
        print(title)

        print(
            "Sessions:",
            result["sessions"]
        )

        print(
            "Mean absolute error:",
            result[
                "mean_absolute_error"
            ]
        )

        print(
            "Exact match:",
            str(
                result[
                    "exact_accuracy_percent"
                ]
            ) + "%"
        )


    print()

    print(
        "Report saved to:"
    )

    print(
        REPORT_FILE
    )

    print()

    print(
        "Important: do not tune thresholds from "
        "unsecured-sensor recordings."
    )

    print(
        "=============================================="
    )
    print()


if __name__ == "__main__":
    main()
