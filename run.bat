@echo off
setlocal

echo Starting LaTeX to Accessible HTML Converter...

where quarto >nul 2>nul
if errorlevel 1 (
    echo Error: Quarto is not installed. Please install it first:
    echo   Visit: https://quarto.org/docs/get-started/
    exit /b 1
)

where pandoc >nul 2>nul
if errorlevel 1 (
    echo Error: pandoc is not installed. Please install it first.
    echo   Windows: https://pandoc.org/installing.html
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo Error: Python is not installed.
    exit /b 1
)

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate
pip install -r requirements.txt
if errorlevel 1 (
    echo Error: Failed to install Python dependencies.
    exit /b 1
)

if not exist uploads mkdir uploads
if not exist output mkdir output

echo Starting Flask application on http://localhost:8000
python app.py
