@echo off
REM 打包 Windows 原生应用 (.exe)。需在 Windows 上运行。
setlocal
cd /d "%~dp0"

if not exist ".venv" (
  echo 未发现 .venv，正在创建并安装依赖...
  py -3.12 -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

echo 开始打包 Windows 应用...
flet build windows

echo 完成。产物在 build\windows\
endlocal
