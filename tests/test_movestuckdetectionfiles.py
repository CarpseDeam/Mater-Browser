"""Tests for move stuck detection files functionality."""
import pytest
from pathlib import Path
import tempfile
import shutil

from src.movestuckdetectionfiles import (
    move_stuck_detection_files,
    MoveResult,
    _move_file,
    _update_test_imports,
)


@pytest.fixture
def temp_project() -> Path:
    """Create a temporary project structure for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    src_dir = temp_dir / "src"
    tests_dir = temp_dir / "tests"
    src_dir.mkdir()
    tests_dir.mkdir()

    source_content = '''"""Stuck detection module."""
class FormProcessorStuckDetection:
    pass
'''
    test_content = '''"""Tests for stuck detection."""
from src.formprocessorstuckdetection import FormProcessorStuckDetection

def test_example():
    pass
'''
    (src_dir / "formprocessorstuckdetection.py").write_text(source_content)
    (tests_dir / "test_formprocessorstuckdetection.py").write_text(test_content)

    yield temp_dir

    shutil.rmtree(temp_dir, ignore_errors=True)


class TestMoveStuckDetectionFiles:
    """Tests for move_stuck_detection_files function."""

    def test_moves_source_file_to_correct_location(self, temp_project: Path) -> None:
        """Source file should be moved to stuck_detection.py."""
        results = move_stuck_detection_files(temp_project)

        assert (temp_project / "src" / "stuck_detection.py").exists()
        assert not (temp_project / "src" / "formprocessorstuckdetection.py").exists()
        assert results[0].success is True

    def test_moves_test_file_to_correct_location(self, temp_project: Path) -> None:
        """Test file should be moved to test_stuck_detection.py."""
        results = move_stuck_detection_files(temp_project)

        assert (temp_project / "tests" / "test_stuck_detection.py").exists()
        assert not (temp_project / "tests" / "test_formprocessorstuckdetection.py").exists()
        assert results[1].success is True

    def test_updates_imports_in_test_file(self, temp_project: Path) -> None:
        """Test file imports should be updated to new module name."""
        move_stuck_detection_files(temp_project)

        test_content = (temp_project / "tests" / "test_stuck_detection.py").read_text()
        assert "from src.stuck_detection import" in test_content
        assert "from src.formprocessorstuckdetection import" not in test_content


class TestMoveFile:
    """Tests for _move_file function."""

    def test_returns_error_when_source_missing(self, temp_project: Path) -> None:
        """Should return error result when source file doesn't exist."""
        source = temp_project / "nonexistent.py"
        dest = temp_project / "dest.py"

        result = _move_file(source, dest)

        assert result.success is False
        assert "not found" in result.error

    def test_returns_error_when_destination_exists(self, temp_project: Path) -> None:
        """Should return error result when destination already exists."""
        source = temp_project / "src" / "formprocessorstuckdetection.py"
        dest = temp_project / "src" / "formprocessorstuckdetection.py"

        result = _move_file(source, dest)

        assert result.success is False
        assert "already exists" in result.error
