"""Move and rename stuck detection files to correct locations."""
import shutil
from pathlib import Path
from typing import NamedTuple


class MoveResult(NamedTuple):
    """Result of file move operation."""
    success: bool
    source: Path
    destination: Path
    error: str | None = None


def move_stuck_detection_files(base_path: Path | None = None) -> list[MoveResult]:
    """Move stuck detection files to their correct locations.

    Args:
        base_path: Base project path. Defaults to parent of src directory.

    Returns:
        List of MoveResult for each file operation.
    """
    if base_path is None:
        base_path = Path(__file__).parent.parent

    base_path = Path(base_path)
    results: list[MoveResult] = []

    moves = [
        (
            base_path / "src" / "formprocessorstuckdetection.py",
            base_path / "src" / "stuck_detection.py",
        ),
        (
            base_path / "tests" / "test_formprocessorstuckdetection.py",
            base_path / "tests" / "test_stuck_detection.py",
        ),
    ]

    for source, destination in moves:
        result = _move_file(source, destination)
        results.append(result)

    test_file = base_path / "tests" / "test_stuck_detection.py"
    if test_file.exists():
        _update_test_imports(test_file)

    return results


def _move_file(source: Path, destination: Path) -> MoveResult:
    """Move a single file from source to destination.

    Args:
        source: Source file path.
        destination: Destination file path.

    Returns:
        MoveResult indicating success or failure.
    """
    if not source.exists():
        return MoveResult(
            success=False,
            source=source,
            destination=destination,
            error=f"Source file not found: {source}",
        )

    if destination.exists():
        return MoveResult(
            success=False,
            source=source,
            destination=destination,
            error=f"Destination already exists: {destination}",
        )

    try:
        shutil.move(str(source), str(destination))
        return MoveResult(success=True, source=source, destination=destination)
    except OSError as e:
        return MoveResult(
            success=False,
            source=source,
            destination=destination,
            error=str(e),
        )


def _update_test_imports(test_file: Path) -> None:
    """Update imports in test file to use new module name.

    Args:
        test_file: Path to the test file.
    """
    content = test_file.read_text(encoding="utf-8")
    updated = content.replace(
        "from src.formprocessorstuckdetection import",
        "from src.stuck_detection import",
    )
    test_file.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    results = move_stuck_detection_files()
    for result in results:
        status = "[OK]" if result.success else "[FAIL]"
        print(f"{status} {result.source.name} -> {result.destination.name}")
        if result.error:
            print(f"  Error: {result.error}")
