import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment with temporary directory for commonplace root."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set the environment variable for the test session
        os.environ["COMMONPLACE_ROOT"] = temp_dir
        yield temp_dir
        # Clean up after all tests
        if "COMMONPLACE_ROOT" in os.environ:
            del os.environ["COMMONPLACE_ROOT"]


@pytest.fixture
def temp_commonplace_root():
    """Provide a fresh temporary directory for individual tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)
