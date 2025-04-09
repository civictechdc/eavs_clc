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
