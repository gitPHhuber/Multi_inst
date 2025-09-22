# Multi Inst Diagnostics

Multi Inst is a cross-platform toolkit for batch diagnostics of flight controllers using the
MultiWii Serial Protocol (MSP). The project targets manufacturing scenarios where multiple USB
connected devices must be probed in parallel, exposing both human readable metrics and raw MSP
payloads for post-processing.

## Features

- MSP v1 framing with checksum validation and automatic wake-up of USB VCP ports.
- Parallel polling of multiple `/dev/ttyACM*` / `/dev/ttyUSB*` devices with per-port JSON reports.
- Decoding of core telemetry (status, attitude, altitude, analog sensors, RC/motors and Betaflight
  meter extensions).
- Threshold evaluation with configurable tolerances for tilt, gyro noise, I²C errors and loop
  jitter.
- Safe file permission handling when executed under `sudo`.

The repository is structured with dedicated packages for transport (`multi_inst/core`), IO
coordination (`multi_inst/io`), command line tooling (`multi_inst/cli`), GUI placeholders
(`multi_inst/gui`), simulation utilities (`multi_inst/sim`) and test suites (`tests/`).

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Run diagnostics against automatically discovered ports:

```bash
multi-inst --out ./out --workers 4
```

Use JSON lines output and explicit port list:

```bash
multi-inst --jsonl /dev/ttyACM0 /dev/ttyACM1
```

Reports are stored as `<UID>.json` (when available) or `DEFECT-xxxxx.json` alongside a `_summary.json`
file.

## Development

- Format the code base with `black` and keep linting clean with `ruff`.
- Run the automated test suite before submitting patches:

```bash
pytest
```

Continuous integration is configured via GitHub Actions to run formatting, linting and tests on
pushes and pull requests.

## Roadmap

The current milestone focuses on MSP transport, multi-port orchestration and reliable JSON
reporting. Upcoming work includes GUI visualisation, simulation tools, advanced analytics and
detailed documentation for production deployment.
