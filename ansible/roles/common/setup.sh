#!/bin/bash

set -eu  # Exit on error

# Variables
DEBIAN_API="https://sources.debian.org/api/src/bash"
DEBIAN_MIRROR="http://deb.debian.org/debian/pool/main/b/bash"
FILES_DIR="files/bash"

# Ensure required directories exist
mkdir -p "$FILES_DIR"

# Fetch the latest stable version of bash (ignoring experimental)
LATEST_VERSION=$(curl -sL "$DEBIAN_API" | jq -r '.versions[] | select(.suites[] | test("experimental") | not) | .version' | head -n1)

if [ -z "$LATEST_VERSION" ]; then
    echo "Failed to determine the latest Debian source package for bash."
    exit 1
fi
echo "Latest version: $LATEST_VERSION"

PACKAGE_NAME="bash_${LATEST_VERSION}.debian.tar.xz"

# Check if package is already downloaded
if [ ! -f "$PACKAGE_NAME" ]; then
    echo "Downloading $PACKAGE_NAME..."
    curl -LO "$DEBIAN_MIRROR/$PACKAGE_NAME"
fi

# Extract the package into tmp/ using the original filename
EXTRACT_DIR="${PACKAGE_NAME%.debian.tar.xz}"
mkdir -p "$EXTRACT_DIR"
echo "Extracting $PACKAGE_NAME into $EXTRACT_DIR..."
tar -xf "$PACKAGE_NAME" -C "$EXTRACT_DIR"

# Copy all skel files in one command
echo "Copying skel files to $FILES_DIR..."
cp "$EXTRACT_DIR/debian/skel."* "$FILES_DIR/"

echo "Done. Extracted files are in $EXTRACT_DIR, and skel files are in $FILES_DIR."
