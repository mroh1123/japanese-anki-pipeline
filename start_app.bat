@echo off
rem Starts the Sheets -> Anki app (runs in WSL) and opens it in your browser.
rem Close this window to stop the app.
cd /d "%~dp0"
start "" cmd /c "timeout /t 8 >nul & start http://localhost:8501"
wsl -e bash -c "venv/bin/streamlit run app.py"
