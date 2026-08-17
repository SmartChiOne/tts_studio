#!/usr/bin/env bash
# 一键运行 TTS Studio（开发模式，桌面窗口）。
# 自动处理两件环境小事：
#   1) Homebrew 的 Python 不自带 CA 证书 —— 用 certifi 的证书
#   2) Flet 首次会下载桌面运行时（约 52MB，来自 GitHub）——
#      若 GitHub 下载受阻，取消下方代理注释走本地代理。
set -e
cd "$(dirname "$0")"

# 首次需创建虚拟环境并安装依赖
if [ ! -d ".venv" ]; then
  echo "首次运行：创建虚拟环境并安装依赖（需 Python 3.10+）..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
else
  source .venv/bin/activate
fi

# 用 certifi 的 CA 证书（解决 Homebrew Python 的 SSL 验证问题）
export SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi,os;print(certifi.where())' 2>/dev/null)"

# 若 GitHub release 下载受阻，取消下面两行注释（填你自己的本地代理端口）：
# export https_proxy=http://127.0.0.1:7890
# export http_proxy=http://127.0.0.1:7890

flet run main.py
