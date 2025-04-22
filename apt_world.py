#!/usr/bin/python3
"""
apt-world - Display a list of packages explicitly installed by the user.

This script parses the dpkg status file (default: /var/lib/dpkg/status)
and the apt extended states file (default: /var/lib/apt/extended_states)
to determine which currently installed packages were installed manually
by a user, rather than automatically as dependencies.

Definition of Manual Installation Used:
A package is considered manually installed if it is currently installed AND
it meets either of the following conditions:
  1. It is explicitly marked with "Auto-Installed: 0" in the extended_states file.
  2. It is NOT listed in the extended_states file at all (implicit manual).

Packages marked "Auto-Installed: 1" are considered automatic dependencies.
"""

import sys
import logging
import argparse
from typing import Dict, List, Optional, Set, Iterator
try:
    # Only import Deb822, as Deb822Paragraph caused issues
    from debian.deb822 import Deb822
except ImportError:
    print("Error: python3-debian library not found.", file=sys.stderr)
    print("Please install it using: sudo apt install python3-debian", file=sys.stderr)
    sys.exit(1)


# --- Constants (Defaults) ---
DEFAULT_DPKG_STATUS_PATH = "/var/lib/dpkg/status"
DEFAULT_APT_EXTENDED_STATES_PATH = "/var/lib/apt/extended_states"

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("apt-world")


# --- Core Functions ---

def get_installed_packages(status_file_path: str) -> Set[str]:
    """
    Parse the specified dpkg status file to identify all currently installed
    packages, returning fully qualified names (package:arch).

    Handles file access errors and basic stanza validation. Exits on critical
    errors preventing the retrieval of installed packages.

    Args:
        status_file_path: Path to the dpkg status file to parse.

    Returns:
        A set containing the fully qualified names (e.g., 'libc6:amd64',
        'python3-requests:all') of all installed packages found.
    """
    installed_packages: Set[str] = set()
    logger.debug(f"Attempting to read dpkg status from: {status_file_path}")

    try:
        with open(status_file_path, 'r', encoding='utf-8') as f:
            # Use Deb822 as the type hint
            pkg: Deb822
            for pkg in Deb822.iter_paragraphs(f):
                if 'Package' not in pkg:
                    logger.warning(f"Found stanza without 'Package' field in {status_file_path}, skipping.")
                    continue

                base_package_name: str = pkg['Package'] # Base name from Package field

                if 'Status' not in pkg:
                    logger.warning(f"Package '{base_package_name}' in {status_file_path} missing 'Status' field, skipping.")
                    continue

                status: str = pkg['Status']
                if ' installed' in status:
                    # Construct the fully qualified name
                    architecture: Optional[str] = pkg.get('Architecture')
                    if architecture and architecture != 'all':
                        # Append architecture if it exists and is not 'all'
                        qualified_name = f"{base_package_name}:{architecture}"
                    else:
                        # Otherwise, use the base name (might implicitly include :all sometimes,
                        # or just be arch-independent) - standard practice is often to
                        # include :all for clarity if arch is 'all'. Let's add it.
                        if architecture == 'all':
                             qualified_name = f"{base_package_name}:all"
                        else:
                             # Should not happen often if arch is missing but pkg installed?
                             # Default to base name if Architecture field is missing.
                             qualified_name = base_package_name
                             logger.debug(f"Package '{base_package_name}' has 'installed' status but no explicit 'Architecture' field.")

                    installed_packages.add(qualified_name)

        logger.debug(f"Found {len(installed_packages)} installed packages in {status_file_path}.")
        return installed_packages

    except FileNotFoundError:
        logger.error(f"Fatal: Dpkg status file not found at {status_file_path}")
        sys.exit(1)
    except PermissionError:
        logger.error(f"Fatal: Permission denied when reading {status_file_path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal: Error reading {status_file_path}: {str(e)}")
        sys.exit(1)


def get_auto_installed_map(extended_states_path: str) -> Dict[str, int]:
    """
    Parse the specified apt extended states file to identify packages
    marked as automatically installed.

    Handles file access errors gracefully by returning an empty map and logging
    a warning, effectively treating all packages as manual if the file is
    missing or unreadable.

    Args:
        extended_states_path: Path to the apt extended_states file to parse.

    Returns:
        A dictionary mapping fully qualified package names to their
        Auto-Installed status (0 = manual, 1 = automatic).
    """
    auto_install_map: Dict[str, int] = {}
    logger.debug(f"Attempting to read apt extended states from: {extended_states_path}")

    try:
        with open(extended_states_path, 'r', encoding='utf-8') as f:
            pkg: Deb822
            for pkg in Deb822.iter_paragraphs(f):
                if 'Package' not in pkg:
                    logger.warning(f"Found stanza without 'Package' field in {extended_states_path}, skipping.")
                    continue

                # The 'Package' field in extended_states *should* already be qualified
                package_name: str = pkg['Package']

                if 'Auto-Installed' in pkg:
                    try:
                        auto_installed_value: int = int(pkg['Auto-Installed'])
                        if auto_installed_value in (0, 1):
                           auto_install_map[package_name] = auto_installed_value
                        else:
                            logger.warning(f"Package '{package_name}' in {extended_states_path} has invalid Auto-Installed value '{pkg['Auto-Installed']}', skipping.")
                    except ValueError:
                        logger.warning(f"Package '{package_name}' in {extended_states_path} has non-integer Auto-Installed value '{pkg['Auto-Installed']}', skipping.")
                        continue

    except FileNotFoundError:
        logger.warning(f"Could not find {extended_states_path}. Assuming all packages are manually installed.")
    except PermissionError:
        logger.warning(f"Permission denied reading {extended_states_path}. Assuming all packages are manually installed.")
    except Exception as e:
        logger.warning(f"Error reading {extended_states_path}: {str(e)}. Assuming all packages are manually installed.")

    logger.debug(f"Found {len(auto_install_map)} packages with explicit auto-install information in {extended_states_path}.")
    return auto_install_map


def get_manually_installed_packages(status_file_path: str, extended_states_path: str) -> List[str]:
    """
    Identify manually installed packages by correlating installed packages
    (from status file) with the auto-install information (from extended states).

    Args:
        status_file_path: Path to the dpkg status file.
        extended_states_path: Path to the apt extended_states file.

    Returns:
        A sorted list of fully qualified names for manually installed packages.
    """
    installed_packages: Set[str] = get_installed_packages(status_file_path)
    auto_install_map: Dict[str, int] = get_auto_installed_map(extended_states_path)
    manually_installed: List[str] = []

    for pkg_name in installed_packages:
        # Now pkg_name from get_installed_packages should be qualified
        auto_status: Optional[int] = auto_install_map.get(pkg_name)
        if auto_status != 1:
            manually_installed.append(pkg_name)

    logger.debug(f"Identified {len(manually_installed)} manually installed packages.")
    return sorted(manually_installed)


def main():
    """
    Main execution function: parses command-line arguments, sets up logging,
    calls functions to find manually installed packages, and prints the result.
    """
    parser = argparse.ArgumentParser(
        description="""
        Displays a list of packages explicitly installed by the user on a Debian system,
        parsing dpkg status and apt extended states files.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
        )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help="Enable verbose (DEBUG level) logging to stderr."
        )
    parser.add_argument(
        '--status-file',
        type=str,
        default=DEFAULT_DPKG_STATUS_PATH,
        help=f"Path to the dpkg status file (default: {DEFAULT_DPKG_STATUS_PATH})."
        )
    parser.add_argument(
        '--extended-states-file',
        type=str,
        default=DEFAULT_APT_EXTENDED_STATES_PATH,
        help=f"Path to the apt extended_states file (default: {DEFAULT_APT_EXTENDED_STATES_PATH})."
        )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled.")

    try:
        logger.debug(f"Using status file: {args.status_file}")
        logger.debug(f"Using extended states file: {args.extended_states_file}")
        manually_installed: List[str] = get_manually_installed_packages(
            args.status_file,
            args.extended_states_file
            )
        if manually_installed:
            logger.debug("Printing manually installed packages:")
            for pkg_name in manually_installed:
                 sys.stdout.write(pkg_name + '\n')
        else:
            logger.debug("No manually installed packages found or identified.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()