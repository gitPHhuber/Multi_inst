# Contributing

Thank you for your interest in improving Multi Inst! The project is still in its early stages and
contributions are very welcome. Please follow the steps below to help keep the workflow smooth.

## Development workflow

1. Fork the repository and create a local virtual environment with Python 3.10 or newer.
2. Install dependencies in editable mode:
   ```bash
   pip install -e .[dev]
   ```
3. Create a feature branch and implement your changes. Please keep commits focused.
4. Ensure formatting and linting succeed:
   ```bash
   black .
   ruff check .
   ```
5. Run the automated tests:
   ```bash
   pytest
   ```
6. Submit a pull request describing the motivation and testing performed.

## Coding guidelines

- Prefer typed function signatures and clear module boundaries (`core/`, `io/`, `cli/`, etc.).
- Avoid silent failures: log or bubble up actionable error messages.
- For MSP related code, keep protocol references in docstrings or comments for maintainability.
- Add or update tests in `tests/` when introducing new behaviour.

## Reporting issues

Bug reports and feature requests can be filed via GitHub Issues. Include environment details,
connected hardware information (where applicable) and reproduction steps to speed up triage.

We appreciate your help in building a robust diagnostic platform for flight controllers!
