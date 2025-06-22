format:
    ruff check --select I --fix .
    ruff format .

publish:
    rm -rf dist
    uv build
    uv publish
