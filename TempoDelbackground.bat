@echo off
REM Cambiar al directorio donde está el script
cd /d %~dp0
REM Ejecutar la aplicación
python tempodel_checker.py
pause
