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

Run diagnostics against automatically discovered ports with the default USB profile:

```bash
multi-inst --out ./out --workers 4 --profile usb_stand
```

Use JSON lines output and explicit port list:

```bash
multi-inst --jsonl /dev/ttyACM0 /dev/ttyACM1
```

Reports are stored as `<UID>.json` (when available) or `DEFECT-xxxxx.json` alongside a `_summary.json`
file.

### Profiles and overrides

Diagnostics thresholds are defined in `config.yaml`. Choose a profile with `--profile` and override
individual limits when necessary:

```bash
multi-inst --profile field_strict --max-gyro-std 4.5 --max-cyc-jitter 12
```

Each JSON report embeds the raw MSP payload for every decoded command, enabling offline re-parsing.

## Factory setup

1. Ensure the `dialout` (or equivalent) group has access to `/dev/ttyACM*` and `/dev/ttyUSB*`. Add the
   production user with `sudo usermod -aG dialout $USER` and re-login.
2. Disable ModemManager or other services that can occupy VCP ports:

   ```bash
   sudo systemctl disable --now ModemManager.service
   ```

3. Install the toolkit into an isolated environment (system-wide via `pipx` or a virtualenv):

   ```bash
   pipx install --include-deps .
   ```

4. Deploy the provided `config.yaml` and optional custom profiles. Use `--config /path/to/config.yaml`
   to point the CLI at a site-specific configuration file.

Output files are created with `664` permissions and re-chowned to the invoking user when the tool is
launched via `sudo`. The target directory is created with `775` permissions to ease sharing between
operators.

### Troubleshooting

- **Only power, no data**: Some USB cables are charge-only; swap to a known-good data cable.
- **Controller stuck in DFU**: Exit DFU mode or reboot the controller before running diagnostics.
- **Port busy**: If you see a "port busy" error, double-check that ModemManager and other serial
  tools are stopped.
- **No UID in filename**: Older firmware may omit `MSP_UID`; the tool falls back to `DEFECT-xxxxx` and
  records the raw responses for offline investigation.

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
