@echo off
setlocal
set "ROOT=%~dp0"
pushd "%ROOT%"

if exist "%ROOT%.venv\Scripts\pythonw.exe" goto :venv

where pyw >nul 2>nul
if %errorlevel%==0 goto :pyw

where pythonw >nul 2>nul
if %errorlevel%==0 goto :pythonw

echo Could not find pythonw.exe/pyw.exe. Create a .venv or install Python (windowed).
goto :done

:venv
start "" "%ROOT%.venv\Scripts\pythonw.exe" "%ROOT%KothCalculator\koth_calculator.py"
goto :done

:pyw
start "" pyw -3 "%ROOT%KothCalculator\koth_calculator.py"
goto :done

:pythonw
start "" pythonw "%ROOT%KothCalculator\koth_calculator.py"

:done
popd
endlocal
