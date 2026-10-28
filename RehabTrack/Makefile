PYTHON ?= python3
GATEWAY_PY := gateway/.venv/bin/python
PIO ?= $(shell sh scripts/find-platformio.sh 2>/dev/null || printf '%s\n' pio)
FIRMWARE_DIR := firmware/xiao_nrf52840_sense

.PHONY: help setup firmware upload monitor analyze quality label evaluate web check clean

help: ; @echo "RehabTrack commands"; echo "  make setup      Create Python environment"; echo "  make firmware   Build XIAO firmware"; echo "  make upload     Upload firmware to XIAO"; echo "  make monitor    Open serial monitor"; echo "  make analyze    Analyze latest repetition test"; echo "  make quality    Check latest sensor recording quality"; echo "  make label      Save true reps for a session"; echo "  make evaluate   Evaluate repetition detection"; echo "  make web        Start RehabTrack dashboard"; echo "  make check      Run RehabTrack system checks"; echo "  make clean      Remove cache files"

setup: ; $(PYTHON) -m venv gateway/.venv && $(GATEWAY_PY) -m pip install --upgrade pip && $(GATEWAY_PY) -m pip install -r gateway/requirements.txt

firmware: ; cd $(FIRMWARE_DIR) && "$(PIO)" run

upload: ; cd $(FIRMWARE_DIR) && "$(PIO)" run --target upload

monitor: ; cd $(FIRMWARE_DIR) && "$(PIO)" device monitor

analyze: ; cd gateway && .venv/bin/python analyze_reps.py

web: ; (sleep 1; open http://127.0.0.1:8000) & $(GATEWAY_PY) gateway/app.py

clean: ; find . -name __pycache__ -type d -prune -exec rm -rf {} +; find . -name "*.pyc" -type f -delete

check:
	$(GATEWAY_PY) -m py_compile gateway/app.py gateway/progress_api.py
	$(GATEWAY_PY) tests/smoke_test.py

quality:
	$(GATEWAY_PY) evaluation/session_quality.py

label:
	@test -n "$(FILE)" || (echo "Usage: make label FILE=session.csv REPS=10"; exit 1)
	@test -n "$(REPS)" || (echo "Usage: make label FILE=session.csv REPS=10"; exit 1)
	$(GATEWAY_PY) evaluation/label_session.py "$(FILE)" "$(REPS)"

evaluate:
	$(GATEWAY_PY) evaluation/evaluate_algorithm.py

sessions:
	@echo ""
	@echo "Latest RehabTrack sessions:"
	@echo ""
	@ls -1t data/raw/rehab001/*.csv 2>/dev/null | head -15 || echo "No sessions found."
	@echo ""

label-latest:
	@test -n "$(EXERCISE)" || (echo "Usage: make label-latest EXERCISE=knee_extension REPS=10"; exit 1)
	@test -n "$(REPS)" || (echo "Usage: make label-latest EXERCISE=knee_extension REPS=10"; exit 1)
	$(GATEWAY_PY) evaluation/label_latest.py "$(EXERCISE)" "$(REPS)"


.PHONY: mobile

mobile:
	@IP=$$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true); \
	echo ""; \
	echo "======================================"; \
	echo "       REHABTRACK MOBILE / PWA"; \
	echo "======================================"; \
	echo "Mac:   http://127.0.0.1:8000"; \
	if [ -n "$$IP" ]; then echo "Phone: http://$$IP:8000"; else echo "Phone: find your Mac IP in Wi-Fi settings"; fi; \
	echo "Press Ctrl+C to stop."; \
	echo ""
	cd gateway && .venv/bin/python -m flask --app app run --host=0.0.0.0 --port=8000
