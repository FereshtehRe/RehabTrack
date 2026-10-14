from pathlib import Path
import webbrowser
import threading
import subprocess
import signal
import time
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

app = Flask(__name__)

logger_process = None
logger_paused = False


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


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/styles.css")
def styles():
    return send_from_directory(WEB_DIR, "styles.css")


@app.route("/app.js")
def javascript():
    return send_from_directory(WEB_DIR, "app.js")




@app.route("/api/start-exercise", methods=["POST"])
def start_exercise():
    global logger_process, logger_paused

    try:
        if logger_process is not None and logger_process.poll() is None:
            return jsonify({
                "error": "An exercise is already running."
            }), 409

        data = request.get_json() or {}
        exercise = data.get("exercise")

        allowed_exercises = {
            "knee_extension",
            "squat"
        }

        if exercise not in allowed_exercises:
            return jsonify({
                "error": "Unknown exercise."
            }), 400

        python_path = BASE_DIR / "gateway" / ".venv" / "bin" / "python"
        logger_path = BASE_DIR / "gateway" / "logger.py"

        logger_process = subprocess.Popen(
            [
                str(python_path),
                str(logger_path),
                "--label", exercise,
                "--cat", "rehab001",
                "--rate", "25"
            ],
            cwd=BASE_DIR / "gateway"
        )

        logger_paused = False

        return jsonify({
            "started": True,
            "exercise": exercise
        })

    except Exception as exc:
        return jsonify({
            "error": str(exc)
        }), 500


@app.route("/api/pause-exercise", methods=["POST"])
def pause_exercise():
    global logger_process, logger_paused

    try:
        if logger_process is None or logger_process.poll() is not None:
            return jsonify({
                "error": "No exercise is running."
            }), 409

        if not logger_paused:
            logger_process.send_signal(signal.SIGSTOP)
            logger_paused = True

        return jsonify({
            "paused": True
        })

    except Exception as exc:
        return jsonify({
            "error": str(exc)
        }), 500



@app.route("/api/resume-exercise", methods=["POST"])
def resume_exercise():
    global logger_process, logger_paused

    try:
        if logger_process is None or logger_process.poll() is not None:
            return jsonify({
                "error": "No exercise is running."
            }), 409

        if not logger_paused:
            return jsonify({
                "error": "Exercise is not paused."
            }), 409

        logger_process.send_signal(signal.SIGCONT)
        logger_paused = False

        return jsonify({
            "resumed": True
        })

    except Exception as exc:
        return jsonify({
            "error": str(exc)
        }), 500


@app.route("/api/stop-exercise", methods=["POST"])
def stop_exercise():
    global logger_process, logger_paused

    try:
        if logger_process is None or logger_process.poll() is not None:
            return jsonify({
                "error": "No exercise is running."
            }), 409

        # A stopped process must be continued before it can
        # handle SIGINT and save the CSV cleanly.
        if logger_paused:
            logger_process.send_signal(signal.SIGCONT)
            time.sleep(0.2)

        logger_process.send_signal(signal.SIGINT)

        try:
            logger_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger_process.terminate()
            logger_process.wait(timeout=2)

        logger_process = None
        logger_paused = False

        return jsonify({
            "stopped": True
        })

    except Exception as exc:
        return jsonify({
            "error": str(exc)
        }), 500




def load_patient_progress():
    default_progress = {
        "knee_extension": {
            "completed_sets": 0,
            "reps_in_set": 0
        },
        "squat": {
            "completed_sets": 0,
            "reps_in_set": 0
        }
    }

    if not PROGRESS_FILE.exists():
        return default_progress

    try:
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return default_progress


def save_patient_progress(progress):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)




@app.route("/api/plan")
def patient_plan():
    try:
        if not PLAN_FILE.exists():
            return jsonify({
                "error": "Patient plan not found."
            }), 404

        with open(PLAN_FILE, "r") as f:
            plan = json.load(f)

        return jsonify(plan)

    except Exception as exc:
        return jsonify({
            "error": str(exc)
        }), 500


@app.route("/api/progress")
def patient_progress():
    return jsonify(load_patient_progress())




@app.route("/api/progress/update", methods=["POST"])
def update_patient_progress():
    try:
        data = request.get_json() or {}

        exercise = data.get("exercise")
        repetitions = int(data.get("repetitions", 0))

        targets = {
            "knee_extension": {
                "sets": 3,
                "reps_per_set": 10
            },
            "squat": {
                "sets": 3,
                "reps_per_set": 10
            }
        }

        if exercise not in targets:
            return jsonify({
                "error": "Unknown exercise."
            }), 400

        if repetitions < 0:
            return jsonify({
                "error": "Invalid repetition count."
            }), 400

        progress = load_patient_progress()

        if exercise not in progress:
            progress[exercise] = {
                "completed_sets": 0,
                "reps_in_set": 0
            }

        target = targets[exercise]
        current = progress[exercise]

        current["reps_in_set"] += repetitions

        while (
            current["reps_in_set"] >= target["reps_per_set"]
            and current["completed_sets"] < target["sets"]
        ):
            current["reps_in_set"] -= target["reps_per_set"]
            current["completed_sets"] += 1

        if current["completed_sets"] >= target["sets"]:
            current["completed_sets"] = target["sets"]
            current["reps_in_set"] = 0

        save_patient_progress(progress)

        return jsonify({
            "exercise": exercise,
            "completed_sets": current["completed_sets"],
            "reps_in_set": current["reps_in_set"],
            "sets": target["sets"],
            "reps_per_set": target["reps_per_set"],
            "exercise_completed":
                current["completed_sets"] >= target["sets"]
        })

    except Exception as exc:
        return jsonify({
            "error": str(exc)
        }), 500


@app.route("/api/session")
def session():
    try:
        filename = request.args.get("file")
        result = analyze_session(filename)

        if result is None:
            return jsonify({"error": "No RehabTrack session found."}), 404

        return jsonify(result)

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def open_browser():
    webbrowser.open("http://127.0.0.1:8000")

@app.route("/api/status")
def status():
    try:
        if not STATUS_FILE.exists():
            return jsonify({
                "connected": False,
                "recording": False
            })

        import json

        with open(STATUS_FILE, "r") as f:
            data = json.load(f)
        files = list(DATA_DIR.glob("*.csv"))

        receiving = False

        if files:
            latest_file = max(files, key=lambda p: p.stat().st_mtime)
            mtime = latest_file.stat().st_mtime
            receiving = (time.time() - mtime) < 5.0
        data["receiving"] = receiving
        return jsonify(data)

    except Exception as exc:
        return jsonify({
            "connected": False,
            "recording": False,
            "error": str(exc)
        }), 500

@app.route("/api/sessions")
def sessions():
    files = sorted(
        DATA_DIR.glob("*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    result = []

    for file_path in files:
        filename = file_path.name
        stat = file_path.stat()

        if filename.startswith("knee_extension_"):
            exercise_id = "knee_extension"
            exercise_name = "Knee Extension"

        elif filename.startswith("squat_"):
            exercise_id = "squat"
            exercise_name = "Squat"

        else:
            exercise_id = "legacy"
            exercise_name = "Previous session"

        repetitions = None

        try:
            analysis = analyze_session(filename)

            if analysis:
                repetitions = analysis.get("repetitions", 0)

        except Exception:
            repetitions = None

        result.append({
            "file": filename,
            "exercise": exercise_id,
            "exercise_name": exercise_name,
            "repetitions": repetitions,
            "modified": time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(stat.st_mtime)
            ),
            "size_kb": round(stat.st_size / 1024, 1)
        })

    return jsonify(result)


if __name__ == "__main__":
    print()
    print("======================================")
    print("          REHABTRACK WEB")
    print("======================================")
    print("Dashboard: http://127.0.0.1:8000")
    print("Press Ctrl+C to stop.")
    print()

    threading.Timer(1.0, open_browser).start()

    app.run(
        host="127.0.0.1",
        port=8000,
        debug=False
    )
