cat > README.md <<'EOF'
# RehabTrack

RehabTrack is a wearable rehabilitation monitoring prototype developed for movement analysis during rehabilitation exercises.

The current prototype uses a Seeed Studio XIAO nRF52840 Sense with an integrated IMU. Sensor data is transmitted over Bluetooth Low Energy (BLE) to a Python application.

## Current features

- Accelerometer data: X, Y, Z
- Gyroscope data: X, Y, Z
- BLE communication
- CSV recording
- Repetition detection
- Relative range of motion (ROM)
- Peak angular velocity / movement speed
- Repetition cadence (reps/min)

## Hardware

- Seeed Studio XIAO nRF52840 Sense
- Integrated LSM6DS3 IMU
- USB or battery power

## Project structure

```text
RehabTrack/
├── firmware/
│   └── xiao_nrf52840_sense/
├── gateway/
│   ├── logger.py
│   ├── analyze_reps.py
│   ├── plot_data.py
│   └── requirements.txt
├── data/
│   ├── raw/
│   └── archive/
├── web/
├── scripts/
├── Makefile
└── README.md