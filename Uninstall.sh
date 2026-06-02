#!/bin/bash
set -e

echo "=== Uninstalling DeltaEdit and GMemo ==="

# Remove symlinks
sudo rm -f /usr/bin/dedit
sudo rm -f /usr/bin/gmemo

# Remove standalone binaries
sudo rm -rf /opt/dedit
sudo rm -rf /opt/gmemo

# Remove metadata, resources, etc.
sudo rm -f /usr/share/applications/DeltaEdit.desktop
sudo rm -f /usr/share/applications/GMemo.desktop
sudo rm -f /usr/share/man/man1/dedit.1.gz
sudo rm -f /usr/share/man/man1/gmemo.1.gz
sudo rm -f /usr/share/pixmaps/gmemo.png
sudo rm -f /usr/share/pixmaps/dedit.png
sudo rm -f /usr/share/pixmaps/dedit_logo.png
sudo rm -rf /etc/dedit

# Update MIME
sudo update-mime-database /usr/share/mime

echo "=== Done! DeltaEdit successfully uninstalled! ==="
