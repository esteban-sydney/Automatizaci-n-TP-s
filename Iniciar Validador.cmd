@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el entorno Python del proyecto.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "Prueba2PDF.py"
if errorlevel 1 pause
