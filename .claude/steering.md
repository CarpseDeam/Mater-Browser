# Project: Mater-Browser

## Stack
- Language: python
- Frameworks: Pydantic
- Tools: mypy, pytest, ruff

## Environment
- Virtual env: `.venv` (Windows)
- Python: `.venv/Scripts/python.exe`
- Run tests: `.venv/Scripts/python.exe -m pytest tests/ -v`
- Install deps: `.venv/Scripts/pip.exe install <pkg>`
## Code Standards
- New files: aim 200-300 lines, split at 400
- Existing files: don't refactor unless >500 lines
- Working god files: leave alone (one responsibility > line count)
- Max function size: 25 lines (40+ ok if one clear purpose)
- Full type hints required
- Use dataclasses/pydantic for structured data
- pathlib over os.path

## Testing
- pytest for all tests
- No mocks unless external service
- Test file mirrors source: src/foo.py → tests/test_foo.py
