@echo off
rem Resident Evil 3: Nemesis (USA) Recompiled - Windows entry point.
rem
rem Opens the game's launcher. In a release package the executable is already
rem built, so nothing else is needed. In a source checkout, the first run
rem builds it with launcher\bootstrap.py, which needs Python 3.11 or newer;
rem the ready-to-run package from the Releases page needs no Python.
setlocal
set "ROOT=%~dp0"
set "EXE=%ROOT%build-release\Resident_Evil_3_Nemesis_USA_Recompiled.exe"

if exist "%EXE%" (
    start "" /D "%ROOT%build-release" "%EXE%" %*
    exit /b 0
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%ROOT%launcher\bootstrap.py" %*
    exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
    python "%ROOT%launcher\bootstrap.py" %*
    exit /b
)

echo The launcher has not been built yet, and Python 3.11 or newer was not found.
echo Download the ready-to-run package from the project's Releases page,
echo or install Python from https://www.python.org and open this file again.
pause
exit /b 1
