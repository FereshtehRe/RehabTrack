from pathlib import Path
import json
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "gateway"))

print()
print("========================================")
print(" RehabTrack system check")
print("========================================")

# --------------------------------------------------
# 1. JSON files
# --------------------------------------------------

json_files = [
    BASE_DIR / "data" / "patient_plan.json",
    BASE_DIR / "data" / "patient_progress.json",
]

for path in json_files:
    if not path.exists():
        raise SystemExit(f"✗ Missing file: {path}")

    try:
        json.loads(path.read_text())
        print(f"✓ Valid JSON: {path.name}")
    except Exception as exc:
        raise SystemExit(
            f"✗ Invalid JSON in {path.name}: {exc}"
        )


# --------------------------------------------------
# 2. Patient plan
# --------------------------------------------------

plan = json.loads(
    (BASE_DIR / "data" / "patient_plan.json").read_text()
)

exercise_ids = {
    item.get("id")
    for item in plan.get("exercises", [])
}

required = {
    "knee_extension",
    "squat",
}

missing = required - exercise_ids

if missing:
    raise SystemExit(
        f"✗ Missing exercises in patient plan: {missing}"
    )

print("✓ Knee Extension assigned")
print("✓ Squat assigned")


# --------------------------------------------------
# 3. Frontend stale API check
# --------------------------------------------------

js = (
    BASE_DIR
    / "web"
    / "app.js"
).read_text()

for stale in [
    "/api/v2/progress",
    "/api/v3/progress",
]:
    if stale in js:
        raise SystemExit(
            f"✗ Frontend still contains stale endpoint: {stale}"
        )

if "/api/rt/progress" not in js:
    raise SystemExit(
        "✗ Frontend does not use /api/rt/progress"
    )

print("✓ Frontend uses clean progress API")
print("✓ No stale V2/V3 progress URLs")


# --------------------------------------------------
# 4. Import Flask app
# --------------------------------------------------

try:
    import app as rehabtrack_app
except Exception as exc:
    raise SystemExit(
        f"✗ Could not import gateway/app.py: {exc}"
    )

client = rehabtrack_app.app.test_client()

print("✓ Flask application imports")


# --------------------------------------------------
# 5. GET endpoints
# --------------------------------------------------

endpoints = [
    "/api/plan",
    "/api/rt/progress",
    "/api/rt/progress/history",
    "/api/day-status-history",
    "/api/sessions",
    "/api/status",
]

for endpoint in endpoints:
    response = client.get(endpoint)

    if response.status_code != 200:
        print()
        print(response.get_data(as_text=True))

        raise SystemExit(
            f"✗ {endpoint} returned "
            f"{response.status_code}"
        )

    print(
        f"✓ {endpoint} -> 200"
    )


# --------------------------------------------------
# 6. Progress payload
# --------------------------------------------------

progress_response = client.get(
    "/api/rt/progress"
)

progress = progress_response.get_json()

if not isinstance(progress, dict):
    raise SystemExit(
        "✗ Progress API did not return an object"
    )

for exercise in required:
    if exercise not in progress:
        raise SystemExit(
            f"✗ Progress missing {exercise}"
        )

    item = progress[exercise]

    if "completed_sets" not in item:
        raise SystemExit(
            f"✗ {exercise}: completed_sets missing"
        )

    if "reps_in_set" not in item:
        raise SystemExit(
            f"✗ {exercise}: reps_in_set missing"
        )

print("✓ Progress structure valid")


# --------------------------------------------------
# 7. Check update route without changing progress
# --------------------------------------------------

response = client.post(
    "/api/rt/progress/update",
    json={
        "exercise": "knee_extension",
        "repetitions": 0,
        "file": None,
    },
)

if response.status_code != 200:
    print(response.get_data(as_text=True))

    raise SystemExit(
        "✗ Progress update endpoint failed"
    )

print("✓ Progress update endpoint works")


print()
print("========================================")
print(" ALL REHABTRACK CHECKS PASSED")
print("========================================")
print()
