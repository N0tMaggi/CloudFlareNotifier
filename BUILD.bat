@echo off
setlocal
pushd %~dp0

echo [1/3] Ensure dependencies are installed...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo [2/3] Build CloudFlareNotifier...
pyinstaller --onefile --noconsole --clean --name CloudFlareNotifier src\main.py

echo [3/3] Build complete. Output: dist\CloudFlareNotifier.exe
popd
