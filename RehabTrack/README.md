# RehabTrack

RehabTrack is a wearable rehabilitation monitoring prototype for home-based knee rehabilitation exercises.

The system uses a Seeed Studio XIAO nRF52840 Sense with an integrated IMU to record movement data. Sensor data is transmitted wirelessly over Bluetooth Low Energy (BLE) to a Python backend, where the data is stored and analyzed. Results are presented through a Flask-based web interface that can be accessed from a computer or mobile device.

## Supported exercises

The current prototype supports:

- Knee Extension
- Squat

Sensor placement depends on the exercise:

- Knee Extension: lower leg
- Squat: thigh

## System architecture

```text
XIAO nRF52840 Sense / IMU
          ↓
         BLE
          ↓
    Python gateway
          ↓
     CSV storage
          ↓
   Movement analysis
          ↓
      Flask API
          ↓
 Web / mobile interface
```

## Features

- Wireless IMU data collection over BLE
- Accelerometer and gyroscope measurements
- Repetition detection
- Relative sensor range of motion (ROM)
- Peak angular velocity / movement speed
- Repetition cadence in reps/min
- Start, pause, resume and stop exercise sessions
- Training plan and progress tracking
- Training history
- CSV-based session storage
- Responsive web interface

The reported ROM represents relative sensor movement and should not be interpreted as an exact anatomical knee joint angle.

## Hardware

- Seeed Studio XIAO nRF52840 Sense
- Integrated LSM6DS3TR-C IMU
- Rechargeable battery
- 3D-printed sensor enclosure
- Adjustable attachment strap

## Software

- Python
- Flask
- HTML
- CSS
- JavaScript
- Bluetooth Low Energy
- PlatformIO

## Validation

Repetition detection was evaluated using controlled trials with manually counted repetitions.

| Exercise / sensor placement | Tests | Manual repetitions | Detected repetitions | MAE |
| --- | ---: | ---: | ---: | ---: |
| Knee Extension – lower leg | 5 × 10 | 50 | 41 | 1.8 reps/test |
| Squat – lower leg | 2 × 10 | 20 | 0 | 10 reps/test |
| Squat – thigh | 5 × 10 | 50 | 50 | 0 reps/test |

The results indicate that sensor placement has a substantial influence on repetition detection for the squat exercise. The current prototype therefore uses exercise-specific sensor placement.

## Project structure

```text
RehabTrack/
├── firmware/
│   └── xiao_nrf52840_sense/
│
├── gateway/
│   ├── analyze_reps.py
│   ├── app.py
│   ├── logger.py
│   ├── progress_api.py
│   └── requirements.txt
│
├── evaluation/
│   ├── evaluate_algorithm.py
│   ├── label_latest.py
│   ├── label_session.py
│   └── session_quality.py
│
├── tests/
│   └── smoke_test.py
│
├── data/
│   ├── algorithm_evaluation.json
│   ├── patient_plan.json
│   ├── patient_progress.json
│   ├── session_labels.json
│   ├── session_quality.json
│   ├── raw/
│   └── processed/
│
├── web/
│   ├── app.js
│   ├── index.html
│   ├── styles.css
│   ├── manifest.webmanifest
│   ├── service-worker.js
│   └── icons/
│
├── scripts/
├── Makefile
└── README.md
```

## Setup

Create the Python environment and install the required dependencies:

```bash
python3 -m venv gateway/.venv
gateway/.venv/bin/python -m pip install -r gateway/requirements.txt
```

## Run RehabTrack

Start the web application with:

```bash
make web
```

The Python backend handles BLE communication, data processing and API functionality. HTML, CSS and JavaScript are used for the user-facing web interface.

## System check

Run the project checks with:

```bash
make check
```

The check verifies the core application, configuration files and API endpoints.

## Evaluation tools

The `evaluation/` directory contains utilities used during controlled testing and validation of the repetition-detection algorithm.

The `tests/` directory contains system-level checks used to verify that the main RehabTrack components work together.

## Limitations

RehabTrack is a prototype and is not intended to provide medical diagnoses.

Current limitations include:

- Validation has been performed on a limited number of controlled trials.
- Repetition detection can vary depending on movement execution and sensor placement.
- IMU integration can introduce drift in estimated sensor rotation.
- Relative sensor ROM is not equivalent to an anatomical knee joint angle.

Future work should include validation with more users, different movement speeds and additional rehabilitation exercises.

