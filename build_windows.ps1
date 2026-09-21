$ErrorActionPreference = 'Stop'
python -m PyInstaller --noconfirm --clean --name NaviVisionStudio --add-data "static;static" app.py
