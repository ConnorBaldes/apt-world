#!/usr/bin/python3
"""
apt-world - Display a list of packages explicitly installed by the user.

This script parses the dpkg status file (default: /var/lib/dpkg/status)
and the apt extended states file (default: /var/lib/apt/extended_states)
to determine which currently installed packages were likely installed manually
by a user, rather than automatically as dependencies.

It supports three modes of operation:

1. Default Mode (Broad Definition):
   Lists all installed packages NOT marked 'Auto-Installed: 1'. This includes
   packages explicitly marked 'Auto-Installed: 0' and packages not found
   in the extended_states file (implicitly manual). This represents all
   packages needed to reconstruct the system beyond the base and automatically
   resolved dependencies.

2. Explicitly Manual Mode (--explicitly-manual):
   Lists only installed packages explicitly marked 'Auto-Installed: 0' in
   the extended_states file. This mode aims to show packages the user or
   an administrator has specifically flagged as manually installed via APT tools.

3. Filter Base Mode (--filter-base):
   Starts with the Default Mode list but then filters out packages that are
   likely part of the essential base system (Essential: yes or Priority: required/important)
   UNLESS those packages are also explicitly marked 'Auto-Installed: 0'.
   This attempts to provide a view closer to user-selected applications and
   libraries, excluding common system infrastructure.
"""

import sys
import logging
import argparse
from typing import Dict, List, Optional, Set, Tuple, Any, Iterator

# Attempt to import python-debian library
try:
    # Only import Deb822, as Deb822Paragraph caused issues previously
    from debian.deb822 import Deb822
except ImportError:
    print("Error: python3-debian library not found.", file=sys.stderr)
    print("Please install it using: sudo apt install python3-debian", file=sys.stderr)
    sys.exit(1)


# --- Constants (Defaults) ---
DEFAULT_DPKG_STATUS_PATH = "/var/lib/dpkg/status"
DEFAULT_APT_EXTENDED_STATES_PATH = "/var/lib/apt/extended_states"

# --- Logging Configuration ---
# Configure root logger for basic output; adjust level in main based on args
logging.basicConfig(
    level=logging.WARNING, # Default level, overridden by --verbose
    format='%(levelname)s: %(message)s',
    stream=sys.stderr # Log messages to stderr
)
# Create a logger instance for explicit logging calls within the script
logger = logging.getLogger(__name__)

# --- Type Hint Alias ---
PackageDetails = Dict[str, Any] # To store priority, essential status etc.

# --- Helper Functions ---

def parse_extended_states(extended_states_path: str) -> Tuple[Set[str], Set[str]]:
    """
    Parses the extended_states file.

    Args:
        extended_states_path (str): Path to the apt extended_states file.

    Returns:
        Tuple[Set[str], Set[str]]: A tuple containing:
            - set of packages marked Auto-Installed: 1 (automatic)
            - set of packages marked Auto-Installed: 0 (explicitly manual)
    """
    automatic_packages: Set[str] = set()
    explicitly_manual_packages: Set[str] = set()
    try:
        logger.debug(f"Parsing extended states file: {extended_states_path}")
        with open(extended_states_path, 'r', encoding='utf-8') as f:
            # Use Deb822.iter_paragraphs for efficient parsing
            for paragraph in Deb822.iter_paragraphs(f):
                auto_installed = paragraph.get('Auto-Installed')
                package_name = paragraph.get('Package')
                architecture = paragraph.get('Architecture')
                if package_name and architecture:
                    pkg_full_name = f"{package_name}:{architecture}"
                    if auto_installed == '1':
                        automatic_packages.add(pkg_full_name)
                    elif auto_installed == '0':
                        explicitly_manual_packages.add(pkg_full_name)
            logger.debug(f"Found {len(automatic_packages)} automatic packages.")
            logger.debug(f"Found {len(explicitly_manual_packages)} explicitly manual packages.")
    except FileNotFoundError:
        # If the file doesn't exist, we can't know which are auto/explicit
        logging.warning(f"Apt extended_states file not found: {extended_states_path}. Cannot determine automatic/explicit status accurately.")
    except Exception as e:
        # Log other potential parsing errors
        logging.error(f"Error parsing Apt extended_states file {extended_states_path}: {e}")
        # Depending on desired robustness, you might exit or just return empty sets
        # Returning empty sets allows operation but results might be less accurate
        # sys.exit(1)
    return automatic_packages, explicitly_manual_packages


def parse_dpkg_status(status_file_path: str) -> Tuple[Set[str], Dict[str, PackageDetails]]:
    """
    Parses the dpkg status file to find installed packages and their details.

    Args:
        status_file_path (str): Path to the dpkg status file.

    Returns:
        Tuple[Set[str], Dict[str, PackageDetails]]: A tuple containing:
         - set of installed packages ('package:arch')
         - dict mapping 'package:arch' to its details (priority, essential)
    """
    installed_packages: Set[str] = set()
    package_details: Dict[str, PackageDetails] = {}
    try:
        logger.debug(f"Parsing dpkg status file: {status_file_path}")
        with open(status_file_path, 'r', encoding='utf-8') as f:
            # Use Deb822.iter_paragraphs for efficient parsing
            for paragraph in Deb822.iter_paragraphs(f):
                # Check the primary 'Status' field for currently installed packages
                if 'install ok installed' in paragraph.get('Status', ''):
                    package_name = paragraph.get('Package')
                    architecture = paragraph.get('Architecture')
                    # Handle cases like 'adduser' which might have 'all' architecture
                    if package_name and architecture:
                        pkg_full_name = f"{package_name}:{architecture}"
                        installed_packages.add(pkg_full_name)
                        # Store details needed for heuristics
                        details: PackageDetails = {
                            'priority': paragraph.get('Priority'),
                            'essential': paragraph.get('Essential') # Will be None if not present
                        }
                        package_details[pkg_full_name] = details
        logger.debug(f"Found {len(installed_packages)} installed packages.")
    except FileNotFoundError:
        logging.error(f"DPKG status file not found: {status_file_path}")
        sys.exit(1) # Essential file, exit if not found
    except Exception as e:
        logging.error(f"Error parsing DPKG status file {status_file_path}: {e}")
        sys.exit(1) # Exit on parsing error for this crucial file
    return installed_packages, package_details

# --- Main Execution ---
def main():
    """Parses arguments and runs the main package identification logic."""
    parser = argparse.ArgumentParser(
        description="Display manually installed Debian packages based on different criteria.",
        formatter_class=argparse.RawDescriptionHelpFormatter, # Preserve formatting in help
        epilog="""\
Modes of Operation:
  Default:          Lists all installed packages not marked 'Auto-Installed: 1'.
  --explicitly-manual: Lists only installed packages marked 'Auto-Installed: 0'.
  --filter-base:    Lists default packages, but filters out likely base system
                    packages (Essential: yes, Priority: required/important)
                    unless they are explicitly marked 'Auto-Installed: 0'.
"""
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

    # Define the mutually exclusive group for filtering modes
    mode_group = parser.add_mutually_exclusive_group()

    mode_group.add_argument(
        '--explicitly-manual',
        action='store_true',
        help="Mode 2: List only packages explicitly marked 'Auto-Installed: 0'."
    )

    mode_group.add_argument(
        '--filter-base',
        action='store_true',
        help="Mode 3: List 'not automatic' packages, filtering likely base packages."
    )

    args = parser.parse_args()

    # Set logging level based on verbose flag
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled.")
    else:
        logger.setLevel(logging.WARNING) # Ensure default is WARNING if not verbose

    # Determine the operating mode
    if args.explicitly_manual:
        operating_mode = "explicit"
    elif args.filter_base:
        operating_mode = "filter_base"
    else:
        operating_mode = "default" # Mode 1

    logger.debug(f"Operating mode selected: {operating_mode}")

    try:
        # 1. Gather all data
        logger.debug(f"Using status file: {args.status_file}")
        logger.debug(f"Using extended states file: {args.extended_states_file}")
        installed_set, package_details_dict = parse_dpkg_status(args.status_file)
        auto_installed_set, explicitly_manual_set = parse_extended_states(args.extended_states_file)

        final_package_set: Set[str] = set() # Initialize empty set for results

        # 2. Apply logic based on mode
        if operating_mode == "explicit":
            logger.debug("Calculating Mode 2: Explicitly Manual (Auto-Installed: 0)")
            # Intersect installed with explicitly marked manual
            final_package_set = installed_set.intersection(explicitly_manual_set)
            logger.debug(f"Resulting packages (installed and Auto-Installed: 0): {len(final_package_set)}")

        elif operating_mode == "filter_base":
            logger.debug("Calculating Mode 3: Filter Base Packages")
            # Start with the default broad list (installed minus automatic)
            default_broad_set = installed_set - auto_installed_set
            logger.debug(f"Initial broad set (not automatic): {len(default_broad_set)}")

            filtered_set: Set[str] = set() # Set to store the filtered results
            for pkg in default_broad_set:
                # Rule 1: Always keep if explicitly marked manual
                if pkg in explicitly_manual_set:
                    filtered_set.add(pkg)
                    logger.debug(f"  Keeping '{pkg}' (explicitly marked manual)")
                    continue # Skip further checks for this package

                # Rule 2: Apply heuristic filters if NOT explicitly marked manual
                details = package_details_dict.get(pkg, {}) # Get details safely
                is_essential = details.get('essential') == 'yes'
                priority = details.get('priority')
                is_base_priority = priority in ('required', 'important')

                # Apply the filter conditions
                if is_essential:
                    logger.debug(f"  Filtering out '{pkg}' (Essential: yes and not explicitly marked)")
                    continue # Filter out
                if is_base_priority:
                    logger.debug(f"  Filtering out '{pkg}' (Priority: {priority} and not explicitly marked)")
                    continue # Filter out

                # If it passed heuristic filters (not essential/required/important)
                logger.debug(f"  Keeping '{pkg}' (passed base filters and not explicitly marked)")
                filtered_set.add(pkg) # Keep the package

            final_package_set = filtered_set
            logger.debug(f"Resulting packages after filtering base: {len(final_package_set)}")

        else: # Default mode
            logger.debug("Calculating Mode 1: Default (Not Automatic)")
            # Installed minus automatically installed
            final_package_set = installed_set - auto_installed_set
            logger.debug(f"Resulting packages (installed and not Auto-Installed: 1): {len(final_package_set)}")


        # 3. Sort and Print Result to Standard Output
        final_package_list = sorted(list(final_package_set))

        if final_package_list:
            logger.debug(f"Printing {len(final_package_list)} packages for mode '{operating_mode}' to stdout.")
            # Output each package name followed by a newline to stdout
            for pkg_name in final_package_list:
                 sys.stdout.write(pkg_name + '\n') # Use '\n' for POSIX newline
            sys.stdout.flush() # Ensure output is written immediately
        else:
            logger.debug(f"No packages found matching the criteria for mode '{operating_mode}'.")

    except Exception as e:
        # Catch-all for unexpected errors during processing
        logger.error(f"An unexpected error occurred: {e}", exc_info=args.verbose) # Show traceback if verbose
        sys.exit(1)

# Standard Python entry point guard
if __name__ == "__main__":
    main()