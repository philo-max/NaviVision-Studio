$ErrorActionPreference = 'Stop'
python -m PyInstaller --noconfirm --clean --name NaviVisionStudio --add-data "static;static" --add-data "samples;samples" app.py
