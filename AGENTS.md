# AGENTS.md - Developer Guidelines for google-app

## Project Overview

- **Language**: Python 3.12+
- **Package Manager**: pyproject.toml (no dependencies currently)
- **Virtual Environment**: `.venv/` (activate with `source .venv/bin/activate`)

---

## Build, Lint, and Test Commands

### Running the Application

```bash
# Run main.py
python main.py

# Or with the virtual environment activated
.venv/bin/python main.py
```

### Testing

```bash
# Run all tests with pytest (recommended)
pytest

# Run a single test file
pytest tests/test_example.py

# Run a single test function
pytest tests/test_example.py::test_function_name

# Run tests matching a pattern
pytest -k "test_pattern"

# Run with verbose output
pytest -v
```

### Linting and Code Quality

```bash
# Run ruff linter (if installed)
ruff check .

# Run ruff with auto-fix
ruff check --fix .

# Run ruff formatter
ruff format .

# Run mypy type checker (if installed)
mypy .
```

### Development Commands

```bash
# Install the package in editable mode
pip install -e .

# Run with auto-reload (if using ruff/other tools)
```

---

## Code Style Guidelines

### General Principles

- Write clean, readable, and idiomatic Python code
- Follow PEP 8 style guide with 88-character line length (Black default)
- Keep functions focused and small (ideally under 30 lines)
- Use meaningful variable and function names

### Imports

- Use absolute imports (e.g., `from package.module import func`)
- Group imports in this order: standard library, third-party, local
- Sort imports alphabetically within each group
- Use `isort` for automatic import sorting
- Example:
  ```python
  # Standard library
  from pathlib import Path
  import sys
  
  # Third-party
  from requests import get
  
  # Local
  from . import module
  from .module import something
  ```

### Formatting

- Use 4 spaces for indentation (no tabs)
- Add trailing commas in multi-line structures
- Use f-strings for string formatting (preferred over .format())
- Maximum line length: 88 characters
- Leave two blank lines between top-level definitions

### Types

- Use type hints for all function arguments and return values
- Prefer explicit types over `Any`
- Use `Optional[T]` instead of `T | None` for Python < 3.10 compatibility, or `T | None` for Python 3.10+
- Example:
  ```python
  def process_data(user_id: int, name: str) -> dict[str, Any]:
      ...
  ```

### Naming Conventions

- **Variables/functions**: `snake_case` (e.g., `user_name`, `calculate_total`)
- **Classes**: `PascalCase` (e.g., `UserAccount`, `DataProcessor`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_RETRIES`, `DEFAULT_TIMEOUT`)
- **Private methods/variables**: prefix with underscore (e.g., `_internal_method`)
- Avoid single-letter variable names except in loops or comprehensions

### Error Handling

- Use specific exception types (e.g., `ValueError`, `FileNotFoundError`)
- Include meaningful error messages
- Use `try/except` only when necessary; let exceptions propagate when appropriate
- Example:
  ```python
  def divide(a: float, b: float) -> float:
      if b == 0:
          raise ValueError("Cannot divide by zero")
      return a / b
  ```

### Documentation

- Use docstrings for all public functions and classes
- Follow Google or NumPy docstring format
- Keep docstrings concise but informative
- Example:
  ```python
  def greet(name: str) -> str:
      """Return a greeting message for the given name.
      
      Args:
          name: The name to greet.
      
      Returns:
          A greeting string.
      """
      return f"Hello, {name}!"
  ```

### Testing Guidelines

- Place tests in a `tests/` directory
- Name test files as `test_<module_name>.py`
- Name test functions as `test_<functionality>`
- Use descriptive assertion messages
- Follow Arrange-Act-Assert pattern

### Git Conventions

- Use meaningful commit messages
- Keep commits atomic and focused
- Create feature branches for new features
- Run linting before committing

---

## File Structure

```
google-app/
├── .venv/              # Virtual environment
├── .gitignore
├── .python-version
├── pyproject.toml      # Project configuration
├── main.py             # Entry point
├── README.md           # Project documentation
└── tests/              # Test files (create this directory)
    └── test_*.py
```

---

## Notes for Agents

- This is a minimal Python project - expand `pyproject.toml` with dependencies as needed
- When adding dependencies, use `pip` or `poetry` to manage them
- Consider adding `ruff`, `pytest`, and `mypy` as development dependencies
- Run `pytest` to verify all tests pass after making changes
- Run `ruff check . && ruff format .` before committing to ensure code quality
