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
        return json.loads(LABEL_FILE.read_text())
    except Exception:
        return {}


parser = argparse.ArgumentParser()

parser.add_argument(
    "exercise",
    choices=[
        "knee_extension",
        "squat"
    ]
)

parser.add_argument(
    "reps",
    type=int
)

args = parser.parse_args()

files = sorted(
    DATA_DIR.glob(
        f"{args.exercise}_*.csv"
    ),
    key=lambda p: p.stat().st_mtime,
    reverse=True
)

if not files:
    raise SystemExit(
        f"No {args.exercise} sessions found."
    )

latest = files[0]

labels = load_labels()

labels[latest.name] = {
    "exercise": args.exercise,
    "expected_reps": args.reps
}

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

print()
print("====================================")
print(" RehabTrack ground truth saved")
print("====================================")
print("File:", latest.name)
print("Exercise:", args.exercise)
print("Actual repetitions:", args.reps)
print("====================================")
print()
