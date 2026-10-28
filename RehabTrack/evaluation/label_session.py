from pathlib import Path
import argparse
import json


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "raw" / "rehab001"
LABEL_FILE = BASE_DIR / "data" / "session_labels.json"


def load_labels():
    if not LABEL_FILE.exists():
        return {}

    try:
        return json.loads(
            LABEL_FILE.read_text()
        )
    except Exception:
        return {}


def save_labels(labels):
    LABEL_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    LABEL_FILE.write_text(
        json.dumps(
            labels,
            indent=2
        )
    )


def infer_exercise(filename):
    if filename.startswith(
        "knee_extension_"
    ):
        return "knee_extension"

    if filename.startswith(
        "squat_"
    ):
        return "squat"

    return "unknown"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Store the manually observed "
            "repetition count for one session."
        )
    )

    parser.add_argument(
        "file",
        help="CSV filename"
    )

    parser.add_argument(
        "reps",
        type=int,
        help="Actual repetitions performed"
    )

    args = parser.parse_args()

    filename = Path(args.file).name

    csv_path = DATA_DIR / filename

    if not csv_path.exists():
        raise SystemExit(
            f"CSV not found: {csv_path}"
        )

    if args.reps < 0:
        raise SystemExit(
            "Repetition count cannot be negative."
        )

    labels = load_labels()

    labels[filename] = {
        "exercise":
            infer_exercise(filename),
        "expected_reps":
            args.reps
    }

    save_labels(labels)

    print()
    print("====================================")
    print(" RehabTrack ground truth saved")
    print("====================================")
    print("File:", filename)
    print(
        "Exercise:",
        labels[filename]["exercise"]
    )
    print("Actual reps:", args.reps)
    print("====================================")
    print()


if __name__ == "__main__":
    main()
