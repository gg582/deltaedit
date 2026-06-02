#!/bin/bash
set -e

echo "=== Preparing Build Environment (venv) ==="
python3 -m venv --system-site-packages build_env
source build_env/bin/activate

echo "=== Installing Build Dependencies ==="
pip install --upgrade pip
pip install nuitka markdown
# Optional packages might fail on certain python versions (like python 3.13), we proceed anyway
pip install tree-sitter tree-sitter-languages || echo "Optional tree-sitter modules failed to install. Continuing build..."


echo "=== Compiling DeltaEdit with Nuitka (Standalone) ==="
cd src
python3 -m nuitka --standalone --enable-plugin=pygobject --assume-yes-for-download dedit.py
python3 -m nuitka --standalone --enable-plugin=pygobject --assume-yes-for-download gmemo.py

echo "=== Installing DeltaEdit and GMemo binaries ==="
sudo mkdir -p /opt/dedit
sudo mkdir -p /opt/gmemo

sudo cp -r --force dedit.dist/* /opt/dedit/
sudo cp -r --force gmemo.dist/* /opt/gmemo/

sudo ln -sf /opt/dedit/dedit /usr/bin/dedit
sudo ln -sf /opt/gmemo/gmemo /usr/bin/gmemo

cd ..

echo "=== Copying resources, metadata, and configuration ==="
sudo mkdir -p /etc/dedit
sudo cp -r --force dedit.png /usr/share/pixmaps/
sudo cp -r --force dedit_logo.png /usr/share/pixmaps/
sudo cp -r --force gmemo.png /usr/share/pixmaps/
sudo cp -r conf/* /etc/dedit/

cd desktop
sudo cp -r --force DeltaEdit.desktop /usr/share/applications/
sudo cp -r --force GMemo.desktop /usr/share/applications/
cd ..

cd man
sudo cp -r --force *.1.gz /usr/share/man/man1/
cd ..

cd etc
sudo cp -r --force * /etc/dedit/
cd ..

sudo chmod +x /usr/share/applications/DeltaEdit.desktop
sudo chmod +x /usr/share/applications/GMemo.desktop

sudo update-mime-database /usr/share/mime

echo "=== Cleaning Up Build Environment ==="
deactivate
rm -rf build_env
rm -rf src/dedit.build src/dedit.dist
rm -rf src/gmemo.build src/gmemo.dist

echo "=== Done! DeltaEdit successfully built and installed! ==="
