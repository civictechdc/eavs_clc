# Print this help documentation
help:
    just --list

# Sync dependencies for the environment
sync:
    uv sync

# Run linting
lint:
    ruff format --check
    ruff check

# Run formatting
format:
    ruff format
    ruff check --fix

# Export dashboard
export-dashboard:
    cp data/cleaned/combined.csv dashboard/public/data/combined.csv
    marimo export html-wasm dashboard/index.py -o _site --mode run
