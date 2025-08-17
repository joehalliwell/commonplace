format:
    ruff check --select I --fix .
    ruff format .

publish:
    rm -rf dist
    uv build
    uv publish

test:
    uv run coverage run --source src --module pytest tests/ -v
    uv run coverage report -m

update-snapshots:
    uv run pytest tests/ --snapshot-update --allow-snapshot-deletion
