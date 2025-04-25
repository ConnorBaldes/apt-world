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
from typing import Dict, List, Optional, Set, Tuple, Any

# Debian package import
try:
    from debian.deb822 import Deb822
except ImportError:
    print("Error: python3-debian library not found.", file=sys.stderr)
    print("Please install it using: sudo apt install python3-debian", file=sys.stderr)
    sys.exit(1)

# Rich library imports
try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text # Import Text for potentially more control
except ImportError:
    print("Error: python3-rich library not found.", file=sys.stderr)
    print("Please install it using: sudo apt install python3-rich", file=sys.stderr)
    sys.exit(1)


# --- Constants (Defaults) ---
DEFAULT_DPKG_STATUS_PATH = "/var/lib/dpkg/status"
DEFAULT_APT_EXTENDED_STATES_PATH = "/var/lib/apt/extended_states"


# --- Logging Configuration (Using Rich) ---
logging.basicConfig(
    level="NOTSET", # Let handler control the effective level
    format="%(message)s", # Basic format, RichHandler overrides
    datefmt="[%X]", # Basic date format, RichHandler overrides
    handlers=[RichHandler(
        level=logging.WARNING, # Default level for the handler (change in main)
        console=Console(stderr=True), # Log to stderr
        show_time=False,
        show_level=True,
        show_path=False, # Set show_path=True in main if verbose
        markup=True,
        rich_tracebacks=True
    )]
)
logger = logging.getLogger("apt_world")


# --- Type Hint Alias ---
PackageDetails = Dict[str, Any]


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
            for paragraph in Deb822.iter_paragraphs(f):
                auto_installed = paragraph.get('Auto-Installed')
                package_name = paragraph.get('Package')
                architecture = paragraph.get('Architecture')
                if package_name and architecture:
                    pkg_full_name = f"{package_name}:{architecture}"
                    if auto_installed == '1':
                        logger.debug(f"  Found automatic: {pkg_full_name}")
                        automatic_packages.add(pkg_full_name)
                    elif auto_installed == '0':
                        logger.debug(f"  Found explicit manual: {pkg_full_name}")
                        explicitly_manual_packages.add(pkg_full_name)
            logger.debug(f" Finished parsing extended_states: {len(automatic_packages)} auto, {len(explicitly_manual_packages)} explicit manual.")
    except FileNotFoundError:
        logging.warning(f"Apt extended_states file not found: {extended_states_path}. Cannot determine automatic/explicit status accurately.")
    except Exception as e:
        logging.error(f"Error parsing Apt extended_states file {extended_states_path}: {e}")
    logger.debug(f" Returning {len(automatic_packages)} auto packages, {len(explicitly_manual_packages)} explicit manual packages.")
    return automatic_packages, explicitly_manual_packages


def parse_dpkg_status(status_file_path: str) -> Tuple[Set[str], Dict[str, PackageDetails]]:
    """
    Parses the dpkg status file to find installed packages and their details.

    Returns:
        Tuple[Set[str], Dict[str, PackageDetails]]: A tuple containing:
         - set of installed packages ('package:arch')
         - dict mapping 'package:arch' to its details (priority, essential, version, section)
    """
    installed_packages: Set[str] = set()
    package_details: Dict[str, PackageDetails] = {}
    try:
        logger.debug(f"Parsing dpkg status file: {status_file_path}")
        with open(status_file_path, 'r', encoding='utf-8') as f:
            for paragraph in Deb822.iter_paragraphs(f):
                status_parts = paragraph.get('Status', '').split()
                is_installed = len(status_parts) >= 3 and status_parts[0] == 'install' and status_parts[1] == 'ok' and status_parts[2] == 'installed'

                if is_installed:
                    package_name = paragraph.get('Package')
                    architecture = paragraph.get('Architecture')
                    if package_name and architecture:
                        pkg_full_name = f"{package_name}:{architecture}"
                        logger.debug(f"  Found installed: {pkg_full_name}")
                        installed_packages.add(pkg_full_name)
                        # Store details needed for heuristics AND display
                        details: PackageDetails = {
                            'priority': paragraph.get('Priority'),
                            'essential': paragraph.get('Essential'),
                            'version': paragraph.get('Version'),
                            'section': paragraph.get('Section')
                        }
                        package_details[pkg_full_name] = details
            logger.debug(f" Finished parsing dpkg_status: Found {len(installed_packages)} installed packages.")
    except FileNotFoundError:
        logging.error(f"DPKG status file not found: {status_file_path}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error parsing DPKG status file {status_file_path}: {e}")
        sys.exit(1)
    logger.debug(f" Returning {len(installed_packages)} installed packages and details for {len(package_details)}.")
    return installed_packages, package_details


# --- Main Execution ---
def main():
    """Parses arguments and runs the main package identification logic."""
    stderr_console = Console(stderr=True)
    stdout_console = Console(file=sys.stdout)

    # Argument Parsing
    parser = argparse.ArgumentParser(
        description="Display manually installed Debian packages based on different criteria.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    # Logging Setup
    log_handler = logging.getLogger().handlers[0]
    if args.verbose:
        log_handler.setLevel(logging.DEBUG)
        log_handler.show_time = True
        log_handler.show_path = True
        logger.debug("Verbose logging enabled.")
    else:
        log_handler.setLevel(logging.WARNING)
        log_handler.show_path = False

    # Mode Determination
    mode_description = ""
    if args.explicitly_manual:
        operating_mode = "explicit"
        mode_title = "Explicitly Manual Packages (Auto-Installed: 0)"
        mode_description = "Showing packages explicitly marked as manually installed (`Auto-Installed: 0`)."
    elif args.filter_base:
        operating_mode = "filter_base"
        mode_title = "Manually Installed Packages (Filtered Base System)"
        mode_description = "Showing 'not automatic' packages, excluding likely base system components unless explicitly marked manual."
    else:
        operating_mode = "default"
        mode_title = "Manually Installed Packages (Not Automatic)"
        mode_description = "Showing all installed packages not marked as automatic dependencies (`Auto-Installed: 1`). Includes implicitly manual packages."
    logger.debug(f"Operating mode selected: [bold cyan]{operating_mode}[/]")


    try:
        # Data Gathering
        logger.debug(f"Using status file: [i]{args.status_file}[/i]")
        logger.debug(f"Using extended states file: [i]{args.extended_states_file}[/i]")
        installed_set, package_details_dict = parse_dpkg_status(args.status_file)
        auto_installed_set, explicitly_manual_set = parse_extended_states(args.extended_states_file)

        # Calculation Logic
        final_package_details: Dict[str, Dict] = {}
        if operating_mode == "explicit":
            logger.debug("Calculating Mode 2: Explicitly Manual (Auto-Installed: 0)")
            explicit_set = installed_set.intersection(explicitly_manual_set)
            for pkg in explicit_set:
                details = package_details_dict.get(pkg, {})
                details['auto_status'] = '0'
                final_package_details[pkg] = details
            logger.debug(f"Resulting packages (installed and Auto-Installed: 0): {len(final_package_details)}")
        elif operating_mode == "filter_base":
            logger.debug("Calculating Mode 3: Filter Base Packages")
            default_broad_set = installed_set - auto_installed_set
            logger.debug(f"Initial broad set (not automatic): {len(default_broad_set)}")
            for pkg in default_broad_set:
                is_explicit = pkg in explicitly_manual_set
                auto_status = '0' if is_explicit else None
                current_details = package_details_dict.get(pkg, {})
                if is_explicit:
                    current_details['auto_status'] = auto_status
                    final_package_details[pkg] = current_details
                    logger.debug(f"  Keeping '{pkg}' (explicitly marked manual)")
                    continue
                is_essential = current_details.get('essential') == 'yes'
                priority = current_details.get('priority')
                is_base_priority = priority in ('required', 'important')
                if is_essential: logger.debug(f"  Filtering out '{pkg}' (Essential: yes)"); continue
                if is_base_priority: logger.debug(f"  Filtering out '{pkg}' (Priority: {priority})"); continue
                current_details['auto_status'] = auto_status
                final_package_details[pkg] = current_details
                logger.debug(f"  Keeping '{pkg}' (passed base filters)")
            logger.debug(f"Resulting packages after filtering base: {len(final_package_details)}")
        else: # Default mode
            logger.debug("Calculating Mode 1: Default (Not Automatic)")
            default_broad_set = installed_set - auto_installed_set
            for pkg in default_broad_set:
                auto_status = '0' if pkg in explicitly_manual_set else None
                details = package_details_dict.get(pkg, {})
                details['auto_status'] = auto_status
                final_package_details[pkg] = details
            logger.debug(f"Resulting packages (installed and not Auto-Installed: 1): {len(final_package_details)}")


        # --- Output Section ---

        # Print Introductory Message
        stdout_console.print(f"\n[bold]apt-world Report[/] ([cyan]{operating_mode}[/] mode)")
        stdout_console.print(f"{mode_description}")
        stdout_console.print(f"Using status file: '[dim]{args.status_file}[/]'")
        stdout_console.print(f"Using states file: '[dim]{args.extended_states_file}[/]'\n")


        # Print Results Table (or 'No packages' message)
        if final_package_details:
            logger.debug(f"Preparing table for {len(final_package_details)} packages.")

            table = Table(show_header=True, header_style="bold magenta", border_style="dim", show_edge=False)
            table.add_column("Package Name", style="cyan", no_wrap=True, min_width=20)
            table.add_column("Arch", style="dim", width=10)
            table.add_column("Version", style="white")
            table.add_column("Auto Status", justify="center")
            table.add_column("Priority", style="blue")
            table.add_column("Section", style="purple")

            sorted_packages = sorted(final_package_details.keys())

            for pkg_full_name in sorted_packages:
                details = final_package_details[pkg_full_name]
                auto_status_val = details.get('auto_status')

                if auto_status_val == '0':
                    status_display = "[green]Explicit[/]"
                else: # None (Implicit)
                    status_display = "[yellow]Implicit[/]"

                parts = pkg_full_name.split(':', 1)
                pkg_name = parts[0]
                arch = parts[1] if len(parts) > 1 else '?'

                version = details.get('version', '?')
                priority = details.get('priority', '?')
                section = details.get('section', '?')

                table.add_row(pkg_name, arch, version, status_display, priority, section)

            output_panel = Panel(
                table,
                title=f"[bold green]{mode_title}[/]",
                subtitle=f"Found [yellow]{len(final_package_details)}[/] packages",
                border_style="blue",
                padding=(0, 1)
            )
            stdout_console.print(output_panel)

        else:
            logger.debug(f"No packages found matching the criteria for mode '[bold cyan]{operating_mode}[/]'.")
            stdout_console.print(Panel(f"No packages found for mode: [bold cyan]{operating_mode}[/]", title="Result", border_style="yellow"))

    # Error Handling
    except FileNotFoundError as e:
         logger.error(f"File not found: {e}", exc_info=args.verbose)
         stderr_console.print(f"[bold red]Error:[/bold red] Required file not found: {e.filename}")
         sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        stderr_console.print(f"[bold red]Error:[/bold red] An unexpected error occurred.")
        stderr_console.print_exception(show_locals=args.verbose)
        sys.exit(1)


# Standard Python entry point guard
if __name__ == "__main__":
    main()

