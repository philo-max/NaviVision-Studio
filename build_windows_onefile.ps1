$ErrorActionPreference = 'Stop'
python -m PyInstaller --noconfirm --clean --distpath dist_onefile --workpath build_onefile NaviVisionStudio_onefile.spec
