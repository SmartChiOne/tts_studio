"""讯飞引擎连通性直测：逐步诊断，不经过界面。

用法：
  python test_xfyun.py                          # 用 GUI 里已保存的凭据
  python test_xfyun.py <app_id> <api_key> <api_secret>   # 直接测试一组新凭据
"""
import asyncio
import os
import sys

from config import load_config
from tts_providers import get_provider


def mask(v: str) -> str:
    if not v:
        return "（空！）"
    return f"{v[:4]}…{v[-2:]}（{len(v)} 字符）"


async def main():
    if len(sys.argv) == 4:
        creds = {"app_id": sys.argv[1], "api_key": sys.argv[2],
                 "api_secret": sys.argv[3]}
        print("（使用命令行传入的凭据）")
    else:
        creds = load_config().get("credentials", {}).get("xfyun", {})

    print("== 第 1 步：检查已保存的凭据 ==")
    for key in ("app_id", "api_key", "api_secret"):
        print(f"  {key:10s} = {mask(creds.get(key, ''))}")
    print("  提示：AppID 一般 8 位数字；APIKey/APISecret 一般 32 位左右，")
    print("        且必须来自讯飞控制台同一应用的「WebAPI 接口」栏。")
    print("        在线语音合成服务需在控制台「我的应用」里领取免费包。")

    print("\n== 第 2 步：尝试合成一句话（xiaoyan） ==")
    p = get_provider("xfyun")
    p.set_credentials(creds)
    out = "/tmp/tts_xfyun_test.mp3"
    try:
        await p.synthesize(
            "你好，这是讯飞引擎的连通性测试。",
            "xiaoyan",
            {"speed": "50", "volume": "50", "pitch": "50"},
            out)
        size = os.path.getsize(out) / 1024
        print(f"  ✓ 成功：{size:.0f} KB -> {out}")
    except RuntimeError as e:
        print(f"  ✗ 失败：{e}")
        print("\n  若提示发音人未授权(11200)：去控制台把 xiaoyan 加入试用。")
        print("  若提示今日次数用完(11201)：每日 500 次，明天再试。")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
