from pathlib import Path
from datetime import date
import json

from flask import Blueprint, jsonify, request


progress_bp = Blueprint(
    "rehabtrack_progress",
    __name__
)

BASE_DIR = Path(__file__).resolve().parents[1]

PLAN_FILE = (
    BASE_DIR
    / "data"
    / "patient_plan.json"
)

PROGRESS_FILE = (
    BASE_DIR
    / "data"
    / "patient_progress.json"
)


def load_plan():
    with open(PLAN_FILE, "r") as f:
        return json.load(f)


def empty_progress():
    plan = load_plan()

    return {
        exercise["id"]: {
            "completed_sets": 0,
            "reps_in_set": 0
        }
        for exercise in plan.get(
            "exercises",
            []
        )
    }


def load_store():
    today = date.today().isoformat()

    if not PROGRESS_FILE.exists():
        return {
            "days": {
                today: empty_progress()
            },
            "processed_sessions": {}
        }

    try:
        raw = PROGRESS_FILE.read_text().strip()
        data = json.loads(raw) if raw else {}

    except Exception:
        data = {}

    # Already using daily format
    if "days" in data:
        data.setdefault(
            "processed_sessions",
            {}
        )

        return data

    # Migrate old flat format
    old_progress = {}

    for key, value in data.items():
        if (
            isinstance(value, dict)
            and "completed_sets" in value
            and "reps_in_set" in value
        ):
            old_progress[key] = value

    if not old_progress:
        old_progress = empty_progress()

    return {
        "days": {
            today: old_progress
        },
        "processed_sessions": {}
    }


def save_store(store):
    PROGRESS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    PROGRESS_FILE.write_text(
        json.dumps(
            store,
            indent=2
        )
    )


def today_progress(store):
    today = date.today().isoformat()

    store.setdefault(
        "days",
        {}
    )

    if today not in store["days"]:
        store["days"][today] = (
            empty_progress()
        )

    defaults = empty_progress()

    for exercise_id, default_value in defaults.items():
        store["days"][today].setdefault(
            exercise_id,
            default_value
        )

    return store["days"][today]


@progress_bp.get("/api/rt/progress")
def get_progress():
    try:
        store = load_store()
        progress = today_progress(store)

        save_store(store)

        return jsonify(progress)

    except Exception as exc:
        print(
            "RT progress error:",
            repr(exc)
        )

        return jsonify({
            "error": str(exc)
        }), 500


@progress_bp.get(
    "/api/rt/progress/history"
)
def get_history():
    try:
        store = load_store()

        today_progress(store)
        save_store(store)

        return jsonify({
            "days": store.get(
                "days",
                {}
            )
        })

    except Exception as exc:
        print(
            "RT history error:",
            repr(exc)
        )

        return jsonify({
            "error": str(exc)
        }), 500


@progress_bp.post(
    "/api/rt/progress/update"
)
def update_progress():
    try:
        payload = (
            request.get_json(
                silent=True
            )
            or {}
        )

        exercise_id = payload.get(
            "exercise"
        )

        session_file = payload.get(
            "file"
        )

        try:
            repetitions = max(
                0,
                int(
                    payload.get(
                        "repetitions",
                        0
                    )
                )
            )

        except Exception:
            repetitions = 0

        plan = load_plan()

        targets = {
            item["id"]: item
            for item in plan.get(
                "exercises",
                []
            )
        }

        if exercise_id not in targets:
            return jsonify({
                "error":
                    "Unknown exercise."
            }), 400

        store = load_store()
        progress = today_progress(store)

        today = date.today().isoformat()

        processed = (
            store
            .setdefault(
                "processed_sessions",
                {}
            )
            .setdefault(
                today,
                []
            )
        )

        target = targets[exercise_id]

        sets_target = max(
            1,
            int(
                target.get(
                    "sets",
                    1
                )
            )
        )

        reps_target = max(
            1,
            int(
                target.get(
                    "reps_per_set",
                    1
                )
            )
        )

        current = progress.setdefault(
            exercise_id,
            {
                "completed_sets": 0,
                "reps_in_set": 0
            }
        )

        # Prevent same CSV from
        # being counted twice.
        if (
            session_file
            and session_file in processed
        ):
            return jsonify({
                "exercise":
                    exercise_id,
                "completed_sets":
                    current[
                        "completed_sets"
                    ],
                "reps_in_set":
                    current[
                        "reps_in_set"
                    ],
                "sets":
                    sets_target,
                "reps_per_set":
                    reps_target,
                "exercise_completed":
                    current[
                        "completed_sets"
                    ] >= sets_target,
                "already_counted":
                    True,
                "file":
                    session_file
            })

        current["reps_in_set"] += (
            repetitions
        )

        while (
            current["reps_in_set"]
            >= reps_target
            and
            current["completed_sets"]
            < sets_target
        ):
            current["reps_in_set"] -= (
                reps_target
            )

            current["completed_sets"] += 1

        if (
            current["completed_sets"]
            >= sets_target
        ):
            current["completed_sets"] = (
                sets_target
            )

            current["reps_in_set"] = 0

        if session_file:
            processed.append(
                session_file
            )

        save_store(store)

        return jsonify({
            "exercise":
                exercise_id,
            "completed_sets":
                current[
                    "completed_sets"
                ],
            "reps_in_set":
                current[
                    "reps_in_set"
                ],
            "sets":
                sets_target,
            "reps_per_set":
                reps_target,
            "exercise_completed":
                current[
                    "completed_sets"
                ] >= sets_target,
            "already_counted":
                False,
            "file":
                session_file
        })

    except Exception as exc:
        print(
            "RT update error:",
            repr(exc)
        )

        return jsonify({
            "error": str(exc)
        }), 500
