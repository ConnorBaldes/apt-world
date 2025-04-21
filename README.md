# Apt World

A Python utility that displays a list of packages explicitly installed by the user on a Debian system.

## Description
This tool parses `/var/lib/dpkg/status` and `/var/lib/apt/extended_states` to identify packages that were manually installed, as opposed to those installed as dependencies.

## Usage
apt-world

## Installation
Install the Debian package:
```bash
sudo apt install ./apt-world_*.deb