#!/usr/bin/env bash
# 打包 macOS 原生应用 (.app)。需在本机 (Mac) 运行。
set -e
cd "$(dirname "$0")"

# 激活虚拟环境（若未创建，先按 README 准备）
if [ ! -d ".venv" ]; then
  echo "未发现 .venv，正在创建并安装依赖..."
  python3.12 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
else
  source .venv/bin/activate
fi

echo "开始打包 macOS 应用..."
flet build macOS

echo "完成。产物在 build/macos/"
