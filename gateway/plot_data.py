import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from pathlib import Path


# ============================================================
# SETTINGS
# ============================================================

DATA_FOLDER = Path("../data/raw/rehab001")

SAMPLE_RATE = 25.0

# Knee extension settings
PROMINENCE = 180
MIN_REP_DISTANCE_SECONDS = 2.0

# A pause longer than this means a new set
REST_THRESHOLD_SECONDS = 9.0

# Smooth signal
SMOOTHING_WINDOW = 7

# Ignore handling of sensor at beginning/end
IGNORE_START_SECONDS = 5
IGNORE_END_SECONDS = 3


# ============================================================
# FIND LATEST CSV
# ============================================================

csv_files = list(DATA_FOLDER.glob("*.csv"))

if not csv_files:
    print("No CSV files found.")
    exit()

file = max(
    csv_files,
    key=lambda f: f.stat().st_mtime
)

print()
print("Analyzing:", file.name)


# ============================================================
# LOAD DATA
# ============================================================

data = pd.read_csv(file)

print("Samples:", len(data))


# ============================================================
# REMOVE START/END HANDLING
# ============================================================

start = int(
    IGNORE_START_SECONDS * SAMPLE_RATE
)

end_remove = int(
    IGNORE_END_SECONDS * SAMPLE_RATE
)

stop = len(data) - end_remove

section = data.iloc[start:stop].copy()


# ============================================================
# TIME
# ============================================================

section["time"] = (
    section.index / SAMPLE_RATE
)


# ============================================================
# USE Y ACCELERATION
# ============================================================

section["signal"] = (
    section["ay_mg"]
    .rolling(
        window=SMOOTHING_WINDOW,
        center=True,
        min_periods=1
    )
    .mean()
)


# ============================================================
# REPETITION DETECTION
# ============================================================

minimum_distance = int(
    MIN_REP_DISTANCE_SECONDS
    * SAMPLE_RATE
)

peaks, properties = find_peaks(
    -section["signal"],   # minus = hitta dalar istället för toppar
    prominence=PROMINENCE,
    distance=minimum_distance
)

peak_times = (
    section["time"]
    .iloc[peaks]
    .to_numpy()
)


# ============================================================
# SET DETECTION
# ============================================================

sets = []

if len(peaks) > 0:

    current_set = [peaks[0]]

    for i in range(1, len(peaks)):

        gap = (
            peak_times[i]
            - peak_times[i - 1]
        )

        if gap > REST_THRESHOLD_SECONDS:

            sets.append(current_set)

            current_set = [peaks[i]]

        else:

            current_set.append(
                peaks[i]
            )

    sets.append(current_set)


# ============================================================
# PRINT RESULT
# ============================================================

print()
print("==============================")
print("REHABTRACK RESULT")
print("==============================")

print(
    "Total repetitions:",
    len(peaks)
)

print(
    "Sets detected:",
    len(sets)
)

print()

for i, detected_set in enumerate(sets):

    print(
        f"Set {i + 1}: "
        f"{len(detected_set)} reps"
    )

print("==============================")


# ============================================================
# PLOT
# ============================================================

plt.figure(figsize=(13, 7))

plt.plot(
    section["time"],
    section["signal"],
    label="Y acceleration"
)


# ============================================================
# MARK REPS
# ============================================================

plt.scatter(
    peak_times,
    section["signal"].iloc[peaks],
    marker="x",
    s=100,
    label="Detected repetition"
)


# Number each repetition
for rep_number, peak in enumerate(peaks):

    x = section["time"].iloc[peak]

    y = section["signal"].iloc[peak]

    plt.text(
    x,
    y - 40,
    str(rep_number + 1),
    ha="center",
    va="top"
)



# ============================================================
# DRAW SET DIVIDERS
# ============================================================

for i in range(len(sets) - 1):

    last_peak_current_set = sets[i][-1]

    first_peak_next_set = sets[i + 1][0]

    time1 = (
        section["time"]
        .iloc[last_peak_current_set]
    )

    time2 = (
        section["time"]
        .iloc[first_peak_next_set]
    )

    divider = (
        time1 + time2
    ) / 2

    plt.axvline(
        divider,
        linestyle="--",
        alpha=0.6
    )


# ============================================================
# GRAPH
# ============================================================

plt.xlabel("Time (s)")
plt.ylabel("Acceleration Y (mg)")

plt.title(
    f"RehabTrack - "
    f"{len(peaks)} repetitions, "
    f"{len(sets)} sets"
)

plt.legend()
plt.grid()

plt.tight_layout()

plt.show()