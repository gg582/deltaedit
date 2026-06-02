#!/bin/bash
set -e

echo "=== Preparing Build Environment (venv) ==="
rm -rf build_env
python3 -m venv --system-site-packages build_env
source build_env/bin/activate

echo "=== Installing Build Dependencies ==="
pip install --upgrade pip
pip install nuitka markdown
pip install tree-sitter tree-sitter-python tree-sitter-rust tree-sitter-c



echo "=== Compiling DeltaEdit with Nuitka (Standalone) ==="
cd src
python3 -m nuitka --standalone --assume-yes-for-download \
  --include-package=gi \
  --include-package=gi.repository \
  --include-package=markdown \
  --include-package=tree_sitter \
  dedit.py
python3 -m nuitka --standalone --assume-yes-for-download \
  --include-package=gi \
  --include-package=gi.repository \
  gmemo.py



echo "=== Installing DeltaEdit and GMemo binaries ==="
sudo mkdir -p /opt/dedit
sudo mkdir -p /opt/gmemo

sudo cp -a dedit.dist/. /opt/dedit/
sudo cp -a gmemo.dist/. /opt/gmemo/

sudo ln -sf /opt/dedit/dedit.bin /usr/bin/dedit
sudo ln -sf /opt/gmemo/gmemo.bin /usr/bin/gmemo

cd ..

echo "=== Copying resources, metadata, and configuration ==="
sudo mkdir -p /etc/dedit
sudo cp -a dedit.png /usr/share/pixmaps/
sudo cp -a dedit_logo.png /usr/share/pixmaps/
sudo cp -a gmemo.png /usr/share/pixmaps/
sudo cp -a conf/* /etc/dedit/

cd desktop
sudo cp -a DeltaEdit.desktop /usr/share/applications/
sudo cp -a GMemo.desktop /usr/share/applications/
cd ..

cd man
sudo cp -a *.1.gz /usr/share/man/man1/
cd ..

cd etc
sudo cp -a * /etc/dedit/
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
