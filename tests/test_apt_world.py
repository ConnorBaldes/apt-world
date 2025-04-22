#!/usr/bin/python3
"""
Tests for the apt-world script using pytest.

Validates the parsing and correlation logic using mock data files,
and tests the command-line interface.
"""

import sys
import os
import pytest # Use pytest
import logging
import subprocess # For testing CLI

# Make the main script importable
# Assumes test file is in 'tests/' and script is in parent directory '.'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import apt_world # Imports apt-world.py

# --- Test Setup ---
TEST_DIR = os.path.dirname(__file__)
MOCK_DATA_DIR = os.path.join(TEST_DIR, "data")

# Define paths to specific mock files (ensure these exist from previous steps)
MOCK_STATUS_BASIC = os.path.join(MOCK_DATA_DIR, "mock_status_basic")
MOCK_ESTATES_BASIC = os.path.join(MOCK_DATA_DIR, "mock_extended_states_basic")
MOCK_STATUS_EMPTY = os.path.join(MOCK_DATA_DIR, "mock_status_empty")
MOCK_ESTATES_EMPTY = os.path.join(MOCK_DATA_DIR, "mock_extended_states_empty")
MOCK_STATUS_NO_INSTALLED = os.path.join(MOCK_DATA_DIR, "mock_status_no_installed")
MOCK_STATUS_ALL_AUTO = os.path.join(MOCK_DATA_DIR, "mock_status_all_auto")
MOCK_ESTATES_ALL_AUTO = os.path.join(MOCK_DATA_DIR, "mock_extended_states_all_auto")
MOCK_STATUS_MALFORMED = os.path.join(MOCK_DATA_DIR, "mock_status_malformed")
MOCK_ESTATES_MALFORMED = os.path.join(MOCK_DATA_DIR, "mock_extended_states_malformed")
MOCK_FILE_NON_EXISTENT = os.path.join(MOCK_DATA_DIR, "non_existent_file")

# --- Helper Function ---
def run_cli(args: list[str]) -> subprocess.CompletedProcess:
    """Helper to run the apt-world script via CLI."""
    script_path = os.path.join(TEST_DIR, '..', 'apt-world.py')
    # Use sys.executable to ensure we use the same python interpreter pytest is using
    command = [sys.executable, script_path] + args
    # Set encoding for consistent text handling
    return subprocess.run(command, capture_output=True, text=True, check=False)

# --- Test Functions ---

# 1. Tests for get_installed_packages()
# =====================================

def test_get_installed_basic():
    """Test parsing installed packages from basic mock status file."""
    packages = apt_world.get_installed_packages(MOCK_STATUS_BASIC)
    expected = {'libc6:amd64', 'python3-requests:all', 'vim-tiny:amd64', 'essential-tool:amd64'}
    assert packages == expected

def test_get_installed_empty():
    """Test parsing installed packages from an empty status file."""
    packages = apt_world.get_installed_packages(MOCK_STATUS_EMPTY)
    assert packages == set()

def test_get_installed_none_installed():
    """Test parsing status file with no packages marked 'installed'."""
    packages = apt_world.get_installed_packages(MOCK_STATUS_NO_INSTALLED)
    assert packages == set()

def test_get_installed_all_auto_status():
    """Test parsing installed packages from the 'all_auto' status file."""
    packages = apt_world.get_installed_packages(MOCK_STATUS_ALL_AUTO)
    expected = {'core-lib:amd64', 'another-lib:all', 'helper-util:amd64'}
    assert packages == expected

def test_get_installed_malformed(caplog):
    """Test parsing malformed status file, checking warnings and results."""
    caplog.set_level(logging.WARNING)
    packages = apt_world.get_installed_packages(MOCK_STATUS_MALFORMED)
    # Only the good package should be found
    assert packages == {'good-package:all'}
    # Check that warnings were logged for the bad stanzas
    assert "Found stanza without 'Package' field" in caplog.text
    assert "Package 'missing-status' in" in caplog.text and "missing 'Status' field" in caplog.text

def test_get_installed_file_not_found():
    """Test that SystemExit is raised if the status file is not found."""
    with pytest.raises(SystemExit) as e:
        apt_world.get_installed_packages(MOCK_FILE_NON_EXISTENT)
    assert e.value.code == 1 # Check exit code


# 2. Tests for get_auto_installed_map()
# ====================================

def test_get_auto_map_basic():
    """Test parsing auto-install info from basic mock extended_states."""
    auto_map = apt_world.get_auto_installed_map(MOCK_ESTATES_BASIC)
    expected = {'libc6:amd64': 1, 'python3-requests:all': 0}
    assert auto_map == expected

def test_get_auto_map_empty():
    """Test parsing auto-install info from empty extended_states."""
    auto_map = apt_world.get_auto_installed_map(MOCK_ESTATES_EMPTY)
    assert auto_map == {}

def test_get_auto_map_file_not_found(caplog):
    """Test parsing when extended_states file is missing."""
    caplog.set_level(logging.WARNING)
    auto_map = apt_world.get_auto_installed_map(MOCK_FILE_NON_EXISTENT)
    assert auto_map == {}
    assert f"Could not find {MOCK_FILE_NON_EXISTENT}" in caplog.text

def test_get_auto_map_all_auto():
    """Test parsing auto-install info from 'all_auto' extended_states."""
    auto_map = apt_world.get_auto_installed_map(MOCK_ESTATES_ALL_AUTO)
    expected = {'core-lib:amd64': 1, 'another-lib:all': 1, 'helper-util:amd64': 1}
    assert auto_map == expected

def test_get_auto_map_malformed(caplog):
    """Test parsing malformed extended_states, checking warnings and results."""
    caplog.set_level(logging.WARNING)
    auto_map = apt_world.get_auto_installed_map(MOCK_ESTATES_MALFORMED)
    # Only the good entry should be parsed
    assert auto_map == {'good-auto:amd64': 1}
    # Check warnings
    assert "Found stanza without 'Package' field" in caplog.text
    assert "Package 'bad-value:all' has non-integer Auto-Installed value 'maybe'" in caplog.text


# 3. Tests for get_manually_installed_packages()
# =============================================

def test_get_manual_basic_scenario():
    """Test identifying manual packages with basic mock files."""
    manual_pkgs = apt_world.get_manually_installed_packages(
        MOCK_STATUS_BASIC, MOCK_ESTATES_BASIC
    )
    # Expected: python3-requests (Auto=0), vim-tiny (not in estates), essential-tool (not in estates)
    expected = ['essential-tool:amd64', 'python3-requests:all', 'vim-tiny:amd64']
    assert sorted(manual_pkgs) == sorted(expected)

def test_get_manual_empty_status():
    """Test identifying manual packages with empty status file."""
    manual_pkgs = apt_world.get_manually_installed_packages(
        MOCK_STATUS_EMPTY, MOCK_ESTATES_BASIC
    )
    assert manual_pkgs == []

def test_get_manual_empty_estates():
    """Test identifying manual packages with empty extended_states file."""
    manual_pkgs = apt_world.get_manually_installed_packages(
        MOCK_STATUS_BASIC, MOCK_ESTATES_EMPTY
    )
    # All installed packages should be considered manual
    expected = ['essential-tool:amd64', 'libc6:amd64', 'python3-requests:all', 'vim-tiny:amd64']
    assert sorted(manual_pkgs) == sorted(expected)

def test_get_manual_missing_estates():
    """Test identifying manual packages with missing extended_states file."""
    manual_pkgs = apt_world.get_manually_installed_packages(
        MOCK_STATUS_BASIC, MOCK_FILE_NON_EXISTENT
    )
    # All installed packages should be considered manual
    expected = ['essential-tool:amd64', 'libc6:amd64', 'python3-requests:all', 'vim-tiny:amd64']
    assert sorted(manual_pkgs) == sorted(expected)

def test_get_manual_no_installed():
    """Test identifying manual packages with no packages marked 'installed'."""
    manual_pkgs = apt_world.get_manually_installed_packages(
        MOCK_STATUS_NO_INSTALLED, MOCK_ESTATES_EMPTY
    )
    assert manual_pkgs == []

def test_get_manual_all_auto():
    """Test identifying manual packages when all installed are marked auto."""
    manual_pkgs = apt_world.get_manually_installed_packages(
        MOCK_STATUS_ALL_AUTO, MOCK_ESTATES_ALL_AUTO
    )
    assert manual_pkgs == [] # Should be empty

def test_get_manual_malformed_files(caplog):
    """Test identifying manual packages with malformed input files."""
    caplog.set_level(logging.WARNING)
    manual_pkgs = apt_world.get_manually_installed_packages(
        MOCK_STATUS_MALFORMED, MOCK_ESTATES_MALFORMED
    )
    # Only 'good-package' is installed and it's not in the valid auto_map entries
    assert sorted(manual_pkgs) == sorted(['good-package:all'])
    # Check that warnings occurred during parsing of underlying files
    assert "missing 'Package' field" in caplog.text # From both files
    assert "missing 'Status' field" in caplog.text # From status
    assert "non-integer Auto-Installed value" in caplog.text # From estates


# 4. Tests for main() / CLI (Exceptional Practice)
# ================================================

def test_cli_basic_run():
    """Test basic CLI execution with mock files."""
    args = ["--status-file", MOCK_STATUS_BASIC, "--extended-states-file", MOCK_ESTATES_BASIC]
    result = run_cli(args)
    expected_output_lines = ['essential-tool:amd64', 'python3-requests:all', 'vim-tiny:amd64']

    assert result.returncode == 0
    # Split stdout lines, strip whitespace, filter empty lines, sort
    actual_output_lines = sorted(filter(None, [line.strip() for line in result.stdout.splitlines()]))
    assert actual_output_lines == sorted(expected_output_lines)
    assert "ERROR:" not in result.stderr
    assert "WARNING:" not in result.stderr

def test_cli_verbose_logging():
    """Test that -v enables DEBUG logging to stderr."""
    args = ["-v", "--status-file", MOCK_STATUS_BASIC, "--extended-states-file", MOCK_ESTATES_BASIC]
    result = run_cli(args)
    assert result.returncode == 0
    # Check stderr for DEBUG messages (specific messages depend on implementation)
    assert "DEBUG: Verbose logging enabled." in result.stderr
    assert "DEBUG: Attempting to read dpkg status from:" in result.stderr
    assert "DEBUG: Attempting to read apt extended states from:" in result.stderr
    assert "DEBUG: Identified" in result.stderr # Part of the manual packages message

def test_cli_status_file_not_found():
    """Test CLI exit code when status file is missing."""
    args = ["--status-file", MOCK_FILE_NON_EXISTENT]
    result = run_cli(args)
    assert result.returncode == 1 # Should exit non-zero
    assert "ERROR: Fatal: Dpkg status file not found" in result.stderr

def test_cli_estates_file_not_found():
    """Test CLI warning when extended_states file is missing."""
    args = ["--status-file", MOCK_STATUS_BASIC, "--extended-states-file", MOCK_FILE_NON_EXISTENT]
    result = run_cli(args)
    assert result.returncode == 0 # Should still exit zero
    assert f"WARNING: Could not find {MOCK_FILE_NON_EXISTENT}" in result.stderr
    # Check stdout is correct (all installed packages are manual)
    expected_output_lines = ['essential-tool:amd64', 'libc6:amd64', 'python3-requests:all', 'vim-tiny:amd64']
    actual_output_lines = sorted(filter(None, [line.strip() for line in result.stdout.splitlines()]))
    assert actual_output_lines == sorted(expected_output_lines)


def test_cli_invalid_argument():
    """Test CLI exit code with an invalid argument."""
    args = ["--nonexistent-argument"]
    result = run_cli(args)
    assert result.returncode != 0 # Should be non-zero (usually 2 for argparse errors)
    assert "usage: apt-world.py" in result.stderr # Should print usage
    assert "unrecognized arguments: --nonexistent-argument" in result.stderr