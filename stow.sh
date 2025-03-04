#!/bin/bash

set -eu

# Determine the base directory of the script
BASE_DIR=$(dirname "$(realpath "$0")")

# Default installation target
TARGET_DIR="/usr/local"

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        -u|--user)
            # Unsupported: systemd units will not work correctly!
            TARGET_DIR="$HOME/.local"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run stow with --no-folding
echo stow --target="$TARGET_DIR" --dir="$BASE_DIR" --no-folding src
stow --target="$TARGET_DIR" --dir="$BASE_DIR" --no-folding src

echo "Stow operation completed."

# Find and print all dead symlinks
find "$TARGET_DIR" -xtype l -print
