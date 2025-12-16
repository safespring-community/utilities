# AGENTS.md

## Overview
Python utilities for migrating OpenStack resources (volumes, instance snapshots) between Safespring cloud platforms (v1 to v2).

## Build/Test/Lint
```bash
pip install -r requirements-dev.txt   # Install dependencies
pytest                                 # Run all tests
pytest tests/test_volume.py           # Run single test file
pytest tests/test_volume.py::TestMigrateSingleVolume::test_dry_run  # Single test
python migrate.py --help              # CLI usage
```
Dependencies: `openstacksdk`, `rich`, `typer`, `qemu-img` (external)

## Code Style Guidelines

### Python
- Target Python 3.10+ with full type hints on all functions
- Use `pathlib.Path` for file paths, never raw strings
- Imports: stdlib first, then third-party, then local (`migration.*`)
- Naming: `snake_case` for functions/variables, `PascalCase` for classes
- Custom exceptions inherit from `MigrationError` in `utils.py`
- Use `@retry` decorator for OpenStack API calls that may fail transiently
- Log via `get_logger()` from utils, not print statements
- Use `rich` console for user-facing output (`print_info`, `print_error`, etc.)
- Docstrings: Google style with Args/Returns/Raises sections
