@echo off
REM 一键运行 TTS Studio（开发模式，桌面窗口）。
setlocal
cd /d "%~dp0"

if not exist ".venv" (
  echo 首次运行：创建虚拟环境并安装依赖（需 Python 3.10+）...
  py -3 -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

REM 用 certifi 的 CA 证书（Windows 的 venv 布局是 Scripts\ 而非 bin\）
for /f "delims=" %%i in ('.venv\Scripts\python -c "import certifi;print(certifi.where())" 2^>nul') do set SSL_CERT_FILE=%%i

REM 若 GitHub release 下载受阻，取消下面两行注释（填你自己的本地代理端口）：
REM set https_proxy=http://127.0.0.1:7890
REM set http_proxy=http://127.0.0.1:7890

flet run main.py
endlocal
