from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

DATA_FOLDER = Path("../data/raw/rehab001")

GYRO_COLUMN = "gy_dps"

BIAS_SECONDS = 5.0

GYRO_DEADBAND = 2.0

MIN_ROM_DEG = 30.0

MIN_REP_DISTANCE_SECONDS = 1.5


# --------------------------------------------------
# LOAD LATEST REP TEST
# --------------------------------------------------

files = list(DATA_FOLDER.glob("rep_test*.csv"))

if not files:
    raise FileNotFoundError("No rep_test CSV found.")

file = max(files, key=lambda f: f.stat().st_mtime)

print(f"Using file: {file.name}")

data = pd.read_csv(file)


# --------------------------------------------------
# TIME
# --------------------------------------------------

data["time_s"] = (
    data["device_ms"] - data["device_ms"].iloc[0]
) / 1000.0

time = data["time_s"].to_numpy()


# --------------------------------------------------
# GYRO BIAS
# --------------------------------------------------

calibration = data[data["time_s"] <= BIAS_SECONDS]

gyro_bias = calibration[GYRO_COLUMN].mean()

print(f"\nGyro bias: {gyro_bias:.2f} deg/s")


gyro = data[GYRO_COLUMN].to_numpy() - gyro_bias


# Remove tiny movements/noise
gyro[np.abs(gyro) < GYRO_DEADBAND] = 0.0


# --------------------------------------------------
# GYRO -> RELATIVE ANGLE
# --------------------------------------------------

angle = np.zeros(len(data))

for i in range(1, len(data)):

    dt = time[i] - time[i - 1]

    if dt <= 0 or dt > 0.2:
        continue

    average_gyro = (gyro[i] + gyro[i - 1]) / 2.0

    angle[i] = angle[i - 1] + average_gyro * dt


data["angle_deg"] = angle


# --------------------------------------------------
# ONLY ANALYZE AFTER CALIBRATION
# --------------------------------------------------

start_index = np.searchsorted(time, BIAS_SECONDS)

movement_angle = angle[start_index:]
movement_time = time[start_index:]


# --------------------------------------------------
# DETERMINE MOVEMENT DIRECTION
# --------------------------------------------------

negative_range = abs(np.min(movement_angle))
positive_range = abs(np.max(movement_angle))

if negative_range > positive_range:

    # Our current bench test rotates mainly negative
    rep_signal = -movement_angle
    direction = "negative"

else:

    rep_signal = movement_angle
    direction = "positive"


print(f"Movement direction: {direction}")


# --------------------------------------------------
# REP DETECTION
# --------------------------------------------------

dt_median = np.median(np.diff(time))

minimum_distance = int(
    MIN_REP_DISTANCE_SECONDS / dt_median
)


peaks, properties = find_peaks(
    rep_signal,
    prominence=MIN_ROM_DEG,
    distance=minimum_distance
)


rep_times = movement_time[peaks]

rep_rom = properties["prominences"]


print(f"\nDetected repetitions: {len(peaks)}")


# --------------------------------------------------
# INTENSITY FOR EACH REP
# --------------------------------------------------

results = []


for i, peak in enumerate(peaks):

    global_peak = peak + start_index

    if i == 0:
        left = start_index
    else:
        previous_peak = peaks[i - 1] + start_index
        left = (previous_peak + global_peak) // 2

    if i == len(peaks) - 1:
        right = len(data)
    else:
        next_peak = peaks[i + 1] + start_index
        right = (global_peak + next_peak) // 2


    rep_gyro = gyro[left:right]

    peak_speed = np.max(np.abs(rep_gyro))

    results.append(
        {
            "rep": i + 1,
            "time": time[global_peak],
            "rom": rep_rom[i],
            "peak_speed": peak_speed,
        }
    )


# --------------------------------------------------
# FREQUENCY / CADENCE
# --------------------------------------------------

if len(rep_times) >= 2:

    intervals = np.diff(rep_times)

    average_interval = np.mean(intervals)

    frequency = 60.0 / average_interval

else:

    frequency = 0.0


# --------------------------------------------------
# PRINT RESULTS
# --------------------------------------------------

print("\n-----------------------------")
print("REHABTRACK SESSION")
print("-----------------------------")

for result in results:

    print(
        f"Rep {result['rep']}: "
        f"ROM = {result['rom']:.1f} deg | "
        f"Intensity = {result['peak_speed']:.1f} deg/s"
    )


print("-----------------------------")

print(f"Repetitions: {len(results)}")

if frequency > 0:
    print(f"Frequency: {frequency:.1f} reps/min")


if results:

    average_rom = np.mean(
        [r["rom"] for r in results]
    )

    average_intensity = np.mean(
        [r["peak_speed"] for r in results]
    )

    print(f"Average ROM: {average_rom:.1f} deg")

    print(
        f"Average intensity: "
        f"{average_intensity:.1f} deg/s"
    )


# --------------------------------------------------
# PLOT
# --------------------------------------------------

plt.figure(figsize=(11, 6))

plt.plot(
    time,
    angle,
    label="Relative angle"
)


for i, peak in enumerate(peaks):

    global_peak = peak + start_index

    plt.scatter(
        time[global_peak],
        angle[global_peak],
        s=70
    )

    plt.annotate(
        f"Rep {i + 1}",
        (
            time[global_peak],
            angle[global_peak]
        ),
        xytext=(0, -25),
        textcoords="offset points",
        ha="center"
    )


plt.axvline(
    BIAS_SECONDS,
    linestyle="--",
    label="End calibration"
)


plt.xlabel("Time [s]")
plt.ylabel("Relative angle [deg]")

plt.title(
    f"RehabTrack - {len(peaks)} repetitions"
)

plt.grid()
plt.legend()

plt.show()