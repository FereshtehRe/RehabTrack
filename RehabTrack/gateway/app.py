import sys
from flask import send_from_directory
import re
from pathlib import Path
import webbrowser
import threading
import subprocess
import signal
import time
from datetime import date
import json
import numpy as np
import pandas as pd
from flask import Flask, jsonify, send_from_directory, request
from scipy.signal import find_peaks


BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data" / "raw" / "rehab001"
STATUS_FILE = BASE_DIR / "data" / "logger_status.json"
PROGRESS_FILE = BASE_DIR / "data" / "patient_progress.json"
PLAN_FILE = BASE_DIR / "data" / "patient_plan.json"
GYRO_COLUMN = "gy_dps"
BIAS_SECONDS = 5.0
GYRO_DEADBAND = 2.0
MIN_ROM_DEG = 30.0
MIN_REP_DISTANCE_SECONDS = 1.5

from progress_api import progress_bp

app = Flask(__name__)


app.register_blueprint(progress_bp)

def open_browser():
    try:
        webbrowser.open_new("http://127.0.0.1:8000")
    except Exception as exc:
        print("Open browser error:", exc)


logger_process = None
logger_paused = False
active_session_file = None
active_exercise_id = None

def write_runtime_status(
    connected=False,
    recording=False,
    paused=False
):
    STATUS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(STATUS_FILE, "w") as f:
        json.dump(
            {
                "connected": connected,
                "recording": recording,
                "paused": paused
            },
            f
        )


def analyze_session(filename=None):

    if filename:
        file_path = DATA_DIR / Path(filename).name

        if not file_path.exists() or file_path.suffix.lower() != ".csv":
            return None 
    else:
        files = sorted(DATA_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime)
        if not files:
            return None
        file_path = files[-1]

    data = pd.read_csv(file_path)



    if "device_ms" not in data.columns or GYRO_COLUMN not in data.columns:
        raise ValueError("CSV is missing required columns.")

    time_s = (data["device_ms"] - data["device_ms"].iloc[0]) / 1000.0
    gyro = data[GYRO_COLUMN].astype(float).to_numpy()

    calibration_mask = time_s <= BIAS_SECONDS
    bias = float(np.mean(gyro[calibration_mask]))

    corrected = gyro - bias
    corrected[np.abs(corrected) < GYRO_DEADBAND] = 0.0

    time_values = time_s.to_numpy()

    angle = np.zeros(len(corrected))

    for i in range(1, len(corrected)):
        dt = time_values[i] - time_values[i - 1]

        if 0 < dt < 1:
            angle[i] = (
                angle[i - 1]
                + ((corrected[i] + corrected[i - 1]) / 2.0) * dt
            )
        else:
            angle[i] = angle[i - 1]

    movement_mask = time_values >= BIAS_SECONDS
    movement_angle = angle[movement_mask]

    # A very short recording may contain no samples
    # after the calibration period. Fall back to all
    # available samples instead of crashing.
    if len(movement_angle) == 0:
        movement_angle = angle

    if len(movement_angle) == 0:
        return {
            "file": file_path.name,
            "gyro_axis": GYRO_COLUMN,
            "gyro_bias": 0.0,
            "direction": "none",
            "repetitions": 0,
            "cadence": 0.0,
            "average_rom": 0.0,
            "average_speed": 0.0,
            "rep_details": [],
            "graph": [],
        }

    negative_range = abs(float(np.min(movement_angle)))
    positive_range = abs(float(np.max(movement_angle)))

    if negative_range >= positive_range:
        direction = "negative"
        rep_signal = -angle
    else:
        direction = "positive"
        rep_signal = angle

    dt_values = np.diff(time_values)
    valid_dt = dt_values[dt_values > 0]

    sample_rate = 25.0

    if len(valid_dt):
        sample_rate = 1.0 / float(np.median(valid_dt))

    minimum_distance = max(
        1,
        int(MIN_REP_DISTANCE_SECONDS * sample_rate)
    )

    peaks, properties = find_peaks(
        rep_signal,
        prominence=MIN_ROM_DEG,
        distance=minimum_distance
    )

    valid_peaks = [
        p for p in peaks
        if time_values[p] >= BIAS_SECONDS
    ]

    peak_lookup = {
        peak: prominence
        for peak, prominence in zip(peaks, properties["prominences"])
    }

    repetitions = []

    for index, peak in enumerate(valid_peaks):
        if index == 0:
            start = 0
        else:
            start = (valid_peaks[index - 1] + peak) // 2

        if index == len(valid_peaks) - 1:
            end = len(corrected)
        else:
            end = (peak + valid_peaks[index + 1]) // 2

        rom = float(peak_lookup[peak])
        peak_speed = float(np.max(np.abs(corrected[start:end])))

        repetitions.append({
            "rep": index + 1,
            "time": round(float(time_values[peak]), 2),
            "rom": round(rom, 1),
            "speed": round(peak_speed, 1),
        })

    if len(valid_peaks) >= 2:
        rep_times = time_values[valid_peaks]
        cadence = 60.0 / float(np.mean(np.diff(rep_times)))
    else:
        cadence = 0.0

    avg_rom = (
        float(np.mean([r["rom"] for r in repetitions]))
        if repetitions else 0.0
    )

    avg_speed = (
        float(np.mean([r["speed"] for r in repetitions]))
        if repetitions else 0.0
    )

    step = max(1, len(time_values) // 300)

    graph = [
        {
            "time": round(float(time_values[i]), 2),
            "angle": round(float(angle[i]), 2)
        }
        for i in range(0, len(time_values), step)
    ]

    return {
        "file": file_path.name,
        "gyro_axis": GYRO_COLUMN,
        "gyro_bias": round(bias, 2),
        "direction": direction,
        "repetitions": len(repetitions),
        "cadence": round(cadence, 1),
        "average_rom": round(avg_rom, 1),
        "average_speed": round(avg_speed, 1),
        "rep_details": repetitions,
        "graph": graph,
    }


@app.route("/api/day-status-history")
def day_status_history():
    """
    Return rehabilitation progress for every known day.

    Modern days come directly from patient_progress.json.

    Older days that existed before daily progress storage
    are reconstructed from saved CSV sessions.
    """
    try:
        # --------------------------------------------------
        # Load patient plan
        # --------------------------------------------------

        try:
            with open(PLAN_FILE, "r") as f:
                plan = json.load(f)
        except Exception:
            plan = {
                "exercises": []
            }

        targets = {
            exercise["id"]: exercise
            for exercise in plan.get(
                "exercises",
                []
            )
        }


        # --------------------------------------------------
        # Load days already stored by progress system
        # --------------------------------------------------

        stored_days = {}

        try:
            if PROGRESS_FILE.exists():
                progress_data = json.loads(
                    PROGRESS_FILE.read_text()
                )

                if isinstance(
                    progress_data.get("days"),
                    dict
                ):
                    stored_days = (
                        progress_data["days"]
                    )

        except Exception as exc:
            print(
                "Historical progress read error:",
                exc
            )


        days = {
            day: progress
            for day, progress
            in stored_days.items()
        }

        day_sources = {
            day: "stored"
            for day in days
        }


        # --------------------------------------------------
        # Find old raw sessions
        # --------------------------------------------------

        session_totals = {}

        filename_pattern = re.compile(
            r"^(knee_extension|squat)_"
            r"(\d{4}-\d{2}-\d{2})_"
            r"\d{2}-\d{2}-\d{2}\.csv$"
        )


        for csv_path in DATA_DIR.glob("*.csv"):

            match = filename_pattern.match(
                csv_path.name
            )

            if not match:
                continue

            exercise_id = match.group(1)
            session_day = match.group(2)

            session_totals.setdefault(
                session_day,
                {}
            )

            session_totals[
                session_day
            ].setdefault(
                exercise_id,
                0
            )


            # Analyze using the same RehabTrack
            # repetition algorithm used elsewhere.
            try:
                analysis = analyze_session(
                    csv_path.name
                )

                repetitions = int(
                    analysis.get(
                        "repetitions",
                        0
                    )
                    if analysis
                    else 0
                )

            except Exception as exc:
                print(
                    "History analysis error:",
                    csv_path.name,
                    exc
                )

                repetitions = 0


            session_totals[
                session_day
            ][exercise_id] += max(
                0,
                repetitions
            )


        # --------------------------------------------------
        # Reconstruct ONLY days that don't already have
        # stored daily progress.
        # --------------------------------------------------

        for session_day, totals in session_totals.items():

            if session_day in days:
                continue


            reconstructed = {
                exercise_id: {
                    "completed_sets": 0,
                    "reps_in_set": 0
                }
                for exercise_id
                in targets
            }


            for exercise_id, repetitions in totals.items():

                if exercise_id not in targets:
                    continue

                target = targets[
                    exercise_id
                ]

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


                max_repetitions = (
                    sets_target *
                    reps_target
                )

                repetitions = min(
                    repetitions,
                    max_repetitions
                )


                completed_sets = min(
                    sets_target,
                    repetitions // reps_target
                )


                if (
                    completed_sets >=
                    sets_target
                ):
                    reps_in_set = 0

                else:
                    reps_in_set = (
                        repetitions %
                        reps_target
                    )


                reconstructed[
                    exercise_id
                ] = {
                    "completed_sets":
                        completed_sets,

                    "reps_in_set":
                        reps_in_set
                }


            days[
                session_day
            ] = reconstructed

            day_sources[
                session_day
            ] = "saved_sessions"


        return jsonify({
            "days": days,
            "day_sources": day_sources
        })


    except Exception as exc:
        print(
            "Day status history error:",
            exc
        )

        return jsonify({
            "error": str(exc)
        }), 500





# ============================================================
# RehabTrack patient plan API
# ============================================================

@app.route("/api/plan")
def rehabtrack_patient_plan_api():
    try:
        import json
        from pathlib import Path

        plan_file = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "patient_plan.json"
        )

        with open(plan_file, "r") as f:
            plan = json.load(f)

        return jsonify(plan)

    except Exception as exc:
        print("Patient plan API error:", exc)

        return jsonify({
            "error": str(exc)
        }), 500




# ============================================================
# RehabTrack session history API
# ============================================================

@app.route("/api/sessions")
def rehabtrack_sessions_api():
    try:
        files = sorted(
            DATA_DIR.glob("*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        sessions = []

        for file_path in files:
            filename = file_path.name

            if filename.startswith("knee_extension_"):
                exercise = "knee_extension"
                exercise_name = "Knee Extension"

            elif filename.startswith("squat_"):
                exercise = "squat"
                exercise_name = "Squat"

            else:
                exercise = "legacy"
                exercise_name = "Previous session"


            repetitions = None
            average_rom = None
            average_speed = None
            cadence = None


            # Old/short CSV files are allowed in history.
            # If analysis fails, the file still appears.
            try:
                result = analyze_session(filename)

                if result:
                    repetitions = result.get(
                        "repetitions"
                    )

                    average_rom = result.get(
                        "average_rom"
                    )

                    average_speed = result.get(
                        "average_speed"
                    )

                    cadence = result.get(
                        "cadence"
                    )

            except Exception:
                pass


            stat = file_path.stat()

            sessions.append({
                "file": filename,
                "exercise": exercise,
                "exercise_name": exercise_name,
                "repetitions": repetitions,
                "average_rom": average_rom,
                "average_speed": average_speed,
                "cadence": cadence,
                "modified": time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(
                        stat.st_mtime
                    )
                ),
                "size_kb": round(
                    stat.st_size / 1024,
                    1
                )
            })


        return jsonify(sessions)


    except Exception as exc:
        print(
            "Sessions API error:",
            exc
        )

        return jsonify({
            "error": str(exc)
        }), 500





# ============================================================
# RehabTrack sensor/runtime status API
# ============================================================

@app.route("/api/status")
def rehabtrack_status_api():
    try:
        status = {
            "connected": False,
            "recording": False,
            "paused": False,
            "receiving": False
        }

        # Read logger/runtime status when available.
        if STATUS_FILE.exists():
            try:
                raw = STATUS_FILE.read_text().strip()

                if raw:
                    stored = json.loads(raw)

                    status["connected"] = bool(
                        stored.get(
                            "connected",
                            False
                        )
                    )

                    status["recording"] = bool(
                        stored.get(
                            "recording",
                            False
                        )
                    )

                    status["paused"] = bool(
                        stored.get(
                            "paused",
                            False
                        )
                    )

            except Exception as exc:
                print(
                    "Status file read error:",
                    exc
                )


        # Determine whether CSV data has arrived recently.
        try:
            files = list(
                DATA_DIR.glob("*.csv")
            )

            if files:
                latest = max(
                    files,
                    key=lambda p:
                        p.stat().st_mtime
                )

                age_seconds = (
                    time.time()
                    - latest.stat().st_mtime
                )

                status["receiving"] = (
                    age_seconds < 5.0
                    and status["connected"]
                )

        except Exception as exc:
            print(
                "Status receiving check error:",
                exc
            )


        return jsonify(status)


    except Exception as exc:
        print(
            "Status API error:",
            exc
        )

        return jsonify({
            "connected": False,
            "recording": False,
            "paused": False,
            "receiving": False,
            "error": str(exc)
        }), 500





# ============================================================
# RehabTrack web interface
# ============================================================

@app.route("/")
def rehabtrack_index():
    return send_from_directory(
        WEB_DIR,
        "index.html"
    )


@app.route("/styles.css")
def rehabtrack_styles():
    return send_from_directory(
        WEB_DIR,
        "styles.css"
    )


@app.route("/app.js")
def rehabtrack_javascript():
    return send_from_directory(
        WEB_DIR,
        "app.js"
    )




# ============================================================
# RehabTrack PWA files
# ============================================================

@app.route("/manifest.webmanifest")
def rehabtrack_manifest():
    return send_from_directory(
        WEB_DIR,
        "manifest.webmanifest",
        mimetype="application/manifest+json"
    )


@app.route("/service-worker.js")
def rehabtrack_service_worker():
    response = send_from_directory(
        WEB_DIR,
        "service-worker.js",
        mimetype="application/javascript"
    )

    response.headers["Cache-Control"] = "no-cache"

    return response


@app.route("/icons/<path:filename>")
def rehabtrack_pwa_icon(filename):
    return send_from_directory(
        WEB_DIR / "icons",
        filename
    )





# ============================================================
# RehabTrack current / historical session API
# ============================================================

@app.route("/api/session")
def rehabtrack_session_api():
    requested_file = request.args.get("file")

    # --------------------------------------------------------
    # Explicit historical session
    # --------------------------------------------------------

    if requested_file:
        safe_name = Path(requested_file).name
        session_path = DATA_DIR / safe_name

        if not session_path.exists():
            return jsonify({
                "error": "Session not found.",
                "file": safe_name
            }), 404

        try:
            result = analyze_session(safe_name)

            if not result:
                raise ValueError(
                    "No analyzable sensor data in session."
                )

            return jsonify(result)

        except Exception as exc:
            return jsonify({
                "error": str(exc),
                "file": safe_name
            }), 422


    # --------------------------------------------------------
    # No file specified:
    # return newest session that can actually be analyzed.
    # --------------------------------------------------------

    files = sorted(
        DATA_DIR.glob("*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    for session_path in files:
        try:
            result = analyze_session(
                session_path.name
            )

            if result:
                return jsonify(result)

        except Exception:
            # Old/short recordings are allowed to exist.
            # Just try the next usable session.
            continue


    # No usable session yet. This is not a server error.
    return jsonify({
        "empty": True,
        "file": None,
        "repetitions": 0,
        "average_rom": 0.0,
        "average_speed": 0.0,
        "cadence": 0.0
    })





# ============================================================
# RehabTrack exercise logger process
# ============================================================

_rehab_logger_process = None
_rehab_logger_paused = False
_rehab_logger_lock = threading.Lock()


def _rehab_normalize_exercise(value):
    if not value:
        return None

    value = str(value).strip().lower()
    value = value.replace("-", "_")
    value = value.replace(" ", "_")

    aliases = {
        "knee_extension": "knee_extension",
        "knee_extensions": "knee_extension",
        "squat": "squat",
        "squats": "squat",
    }

    return aliases.get(value)


def _rehab_process_running():
    global _rehab_logger_process

    return (
        _rehab_logger_process is not None
        and _rehab_logger_process.poll() is None
    )




# ============================================================
# Exercise controls
# ============================================================

@app.route("/api/start-exercise", methods=["POST"])
def rehabtrack_start_exercise():
    global _rehab_logger_process
    global _rehab_logger_paused

    payload = request.get_json(silent=True) or {}

    raw_exercise = (
        payload.get("exercise")
        or payload.get("exercise_id")
        or payload.get("label")
        or request.form.get("exercise")
        or request.form.get("exercise_id")
        or request.form.get("label")
    )

    exercise = _rehab_normalize_exercise(
        raw_exercise
    )

    if exercise is None:
        return jsonify({
            "ok": False,
            "error": "Unknown exercise.",
            "received": raw_exercise
        }), 400

    with _rehab_logger_lock:

        if _rehab_process_running():
            return jsonify({
                "ok": False,
                "error": "An exercise session is already running."
            }), 409

        logger_path = (
            BASE_DIR
            / "gateway"
            / "logger.py"
        )

        command = [
            sys.executable,
            str(logger_path),
            "--label",
            exercise,
            "--cat",
            "rehab001",
            "--rate",
            "25",
        ]

        try:
            _rehab_logger_process = subprocess.Popen(
                command,
                cwd=str(BASE_DIR / "gateway")
            )

            _rehab_logger_paused = False

        except Exception as exc:
            _rehab_logger_process = None

            return jsonify({
                "ok": False,
                "error": str(exc)
            }), 500

    return jsonify({
        "ok": True,
        "exercise": exercise,
        "state": "starting"
    })


@app.route("/api/pause-exercise", methods=["POST"])
def rehabtrack_pause_exercise():
    global _rehab_logger_paused

    with _rehab_logger_lock:

        if not _rehab_process_running():
            return jsonify({
                "ok": False,
                "error": "No active exercise session."
            }), 409

        if not _rehab_logger_paused:
            _rehab_logger_process.send_signal(
                signal.SIGSTOP
            )

            _rehab_logger_paused = True

    return jsonify({
        "ok": True,
        "state": "paused"
    })


@app.route("/api/resume-exercise", methods=["POST"])
def rehabtrack_resume_exercise():
    global _rehab_logger_paused

    with _rehab_logger_lock:

        if not _rehab_process_running():
            return jsonify({
                "ok": False,
                "error": "No active exercise session."
            }), 409

        if _rehab_logger_paused:
            _rehab_logger_process.send_signal(
                signal.SIGCONT
            )

            _rehab_logger_paused = False

    return jsonify({
        "ok": True,
        "state": "recording"
    })


@app.route("/api/stop-exercise", methods=["POST"])
def rehabtrack_stop_exercise():
    global _rehab_logger_process
    global _rehab_logger_paused

    with _rehab_logger_lock:

        if not _rehab_process_running():
            _rehab_logger_process = None
            _rehab_logger_paused = False

            return jsonify({
                "ok": True,
                "state": "stopped"
            })

        process = _rehab_logger_process

        try:
            # A paused process must continue before receiving SIGINT.
            if _rehab_logger_paused:
                process.send_signal(
                    signal.SIGCONT
                )

            process.send_signal(
                signal.SIGINT
            )

            try:
                process.wait(
                    timeout=5
                )

            except subprocess.TimeoutExpired:
                process.terminate()

                try:
                    process.wait(
                        timeout=2
                    )

                except subprocess.TimeoutExpired:
                    process.kill()

        finally:
            _rehab_logger_process = None
            _rehab_logger_paused = False

    return jsonify({
        "ok": True,
        "state": "stopped"
    })


if __name__ == "__main__":
    print()
    print("======================================")
    print("          REHABTRACK WEB")
    print("======================================")
    print("Dashboard: http://127.0.0.1:8000")
    print("Press Ctrl+C to stop.")
    print()


    app.run(
        host="127.0.0.1",
        port=8000,
        debug=False
    )
