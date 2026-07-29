# Run tests and generate coverage report
test:
    uv run coverage run --source src --module pytest tests/ -v -ra --log-cli-level=INFO
    uv run coverage report -m

# Format and fix
format:
    uv run ruff check --fix .
    uv run ruff format .

# Check exactly what CI checks
lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy src/

# Publish package to PyPI
publish:
    rm -rf dist
    uv build
    uv publish

# Update test snapshots
update-snapshots:
    uv run pytest tests/test_import.py --snapshot-update --allow-snapshot-deletion
