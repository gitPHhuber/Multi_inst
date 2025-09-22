.PHONY: test pytest lint format

install:
@pip install -e .[dev]

test: pytest

pytest:
pytest

lint:
ruff check .

format:
black .
