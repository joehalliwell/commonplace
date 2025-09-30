# Run tests and generate coverage report
test:
    uv run coverage run --source src --module pytest tests/ -v -ra --log-cli-level=INFO
    uv run coverage report -m

# Format and fix
format:
    ruff check --select I --fix .
    ruff format .

# Publish package to PyPI
publish:
    rm -rf dist
    uv build
    uv publish

# Update test snapshots
update-snapshots:
    uv run pytest tests/ --snapshot-update --allow-snapshot-deletion
