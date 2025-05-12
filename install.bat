@echo off
title Tempodel Installer

echo.
echo Iniciando la instalacion de Tempodel...
echo.

:FindScriptPath
echo Buscando la ruta de instalacion...
set SCRIPT_PATH=%~dp0
echo Ruta de instalacion detectada: "%SCRIPT_PATH%"

:FindPython
echo.
echo Buscando la ruta de Python...
for %%a in ("%ProgramFiles%\Python310\pythonw.exe" "%ProgramFiles(x86)%\Python310\pythonw.exe") do (
    if exist %%a (
        set PYTHON_PATH=%%a
        goto :PythonFound
    )
)
echo No se encontro Python 3.10 en las rutas estandar.
echo Asegurate de que Python 3.10 este instalado y en tu PATH.
echo Si esta instalado en una ubicacion diferente, deberas modificar este script.
pause
exit /b 1

:PythonFound
echo Python encontrado: "%PYTHON_PATH%"

:SetIconPath
set ICON_PATH="%SCRIPT_PATH%icon.ico"
echo Ruta del icono: "%ICON_PATH%"

:CheckIcon
if not exist "%ICON_PATH%" (
    echo.
    echo Advertencia: No se encontro el archivo "icon.ico" en la carpeta del script.
    echo El menu contextual no mostrara un icono.
    set ICON_PATH=
)

:ModifyRegFile
echo.
echo Modificando el archivo de registro...
set "regfile=%SCRIPT_PATH%tempodel_install_template.reg"
set "outfile=%SCRIPT_PATH%tempodel_install.reg"

if not exist "%regfile%" (
    echo Error: No se encontro el archivo de registro template "%regfile%".
    pause
    exit /b 1
)

(
    for /f "delims=" %%i in ('type "%regfile%"') do (
        set "line=%%i"
        setlocal enabledelayedexpansion
        set "line=!line:%%PYTHON_PATH%=%PYTHON_PATH%!"
        set "line=!line:%%SCRIPT_PATH%=%SCRIPT_PATH:~0,-1%!"  
        set "line=!line:%%ICON_PATH%=%ICON_PATH%!"
        echo(!line!
        endlocal
    )
) > "%outfile%"

if not exist "%outfile%" (
    echo Error: No se pudo crear el archivo de registro modificado "%outfile%".
    pause
    exit /b 1
)

:ImportRegFile
echo.
echo Importando el archivo de registro...
if exist "%SCRIPT_PATH%run_reg_silently.vbs" (
    echo Usando run_reg_silently.vbs para importacion silenciosa...
    cscript //nologo "%SCRIPT_PATH%run_reg_silently.vbs" "%outfile%"
    if %errorlevel% neq 0 (
        echo Error: La importacion silenciosa del registro fallo.
        pause
        exit /b 1
    )
) else (
    echo Importando el registro con regedit (puede mostrar una ventana)...
    reg import "%outfile%"
    if %errorlevel% neq 0 (
        echo Error: La importacion del registro fallo.
        pause
        exit /b 1
    )
)

:Success
echo.
echo Tempodel instalado correctamente.
echo Puede que necesites reiniciar el Explorador de Windows o reiniciar la sesion
echo para que los cambios en el menu contextual surtan efecto.
pause
exit /b 0