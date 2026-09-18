# test_cv_generator.py
import pytest
from pathlib import Path

def test_output_directory_exists():
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    assert output_dir.exists()