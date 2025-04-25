# Apt World

A Python utility for Debian systems that displays a list of installed packages considered "manually installed".

## Description

`apt-world` parses `/var/lib/dpkg/status` and `/var/lib/apt/extended_states` to identify packages that were likely installed directly by the user, rather than automatically as dependencies of other packages.

It aims to provide output similar to the 'selected' set in Gentoo Portage or `apt-mark showmanual`, but with slightly different logic (especially regarding packages missing from `extended_states`).

## Features

* Identifies manually installed packages based on `dpkg` and `apt` state files.
* Supports multiple modes for defining "manual":
    * **Default:** Packages not marked `Auto-Installed: 1` (includes implicitly manual).
    * **Explicitly Manual (`--explicitly-manual`):** Only packages marked `Auto-Installed: 0`.
    * **Filter Base (`--filter-base`):** Default mode, but attempts to exclude base system packages unless explicitly marked manual.
* Uses the `rich` library to present results in a clear, formatted table.
* Provides options for verbose logging and specifying alternative status file paths.
* Relies on the robust `python3-debian` library for parsing state files.
* Adheres to PEP 668 (avoids interfering with user `pip` installs).

## Prerequisites

* A Debian 12 "Bookworm" system (or a compatible derivative).
* The package depends on `python3`, `python3-debian`, and `python3-rich`, which will be installed automatically when using the `.deb` package.

## Installation

You need the generated Debian package file (e.g., `apt-world_0.1-1_all.deb`). Place it in your current directory and run:

```bash
sudo apt update
sudo apt install ./apt-world_*.deb
```
(Note: Replace apt-world_*.deb with the exact filename)

## Usage
### Basic Usage (Default Mode)
Simply run the command:

```Bash
apt-world
```
This will display a table of installed packages not marked as automatic dependencies.

### Using Different Modes
- Explicitly Manual Mode: Show only packages explicitly marked Auto-Installed: 0.
```Bash
apt-world --explicitly-manual
```

- Filter Base Mode: Show non-automatic packages, attempting to hide common base system components.
```Bash
apt-world --filter-base
```

### Other Options
- Verbose Output: Get detailed debug messages sent to stderr.
```Bash
apt-world -v
# or combined with a mode
apt-world --filter-base -v
```

- Specify Custom File Paths: (Useful for testing or examining non-standard systems)
```Bash
apt-world --status-file /path/to/custom/status --extended-states-file /path/to/custom/extended_states
```

- Get Help: Display command-line help.
```Bash
apt-world -h
# or
apt-world --help
```

## Viewing the Man Page
Once installed, you can view the full documentation via the man page:
```Bash
man apt-world
```

## License
This project is licensed under the MIT License (Expat). See the debian/copyright file for full details.

### Author
Connor Baldes <connorbaldes@gmail.com> (2024-2025)

