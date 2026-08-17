"""核心功能验证：Provider 抽象层 + Edge 引擎（不依赖 GUI）。"""
import asyncio
import os

from mutagen.mp3 import MP3

from tts_providers import list_providers, get_provider
from voice_cache import save_cache


async def main():
    print("已注册引擎:", [p.name for p in list_providers()])

    p = get_provider("edge")
    print(f"\n引擎: {p.name}")
    print(f"输出格式: {p.supported_formats()}")
    print("可配参数:", [(s.key, s.label, s.fmt) for s in p.configurable_params()])

    # 声音列表（联网）
    voices = await p.list_voices()
    print(f"\n声音总数: {len(voices)}")
    zh = [v for v in voices if v.language == "zh"]
    print(f"中文声音: {len(zh)}，示例: {zh[0].id if zh else '无'} -> {zh[0].display_name if zh else ''}")
    save_cache("edge", voices)
    print("已缓存到本地")

    # 合成测试
    text = "你好，这是 TTS Studio 的合成测试。佛学用缘起性空的眼光看世界，用戒定慧的路径修自身。"
    params = {"rate": "+0%", "volume": "+0%", "pitch": "+0Hz"}
    out = "/tmp/tts_studio_test.mp3"
    last = [0]

    def on_progress(written, total, seconds=None):
        if written - last[0] > 20000:
            pct = f"{min(written / total, 0.95):.0%}" if total else "?"
            print(f"  进度: {pct} · {written/1024:.0f} KB")
            last[0] = written

    print("\n开始合成...")
    await p.synthesize(text, "zh-CN-XiaoxiaoNeural", params, out, progress_cb=on_progress)

    audio = MP3(out)
    dur = audio.info.length
    size = os.path.getsize(out) / 1024
    print(f"\n✓ 合成完成: 时长 {dur:.1f} 秒, {size:.0f} KB -> {out}")

    # 讯飞引擎自检（静态部分，不联网、不需要凭据）
    from tts_providers.xfyun import XfyunTTSProvider, split_text
    x = XfyunTTSProvider()
    print(f"\n引擎: {x.name}")
    print("凭据:", [(c.key, c.secret) for c in x.credential_specs()])
    print("参数:", [(s.key, s.default) for s in x.configurable_params()])
    voices = await x.list_voices()
    print(f"内置发音人: {[v.id for v in voices]}")
    chunks = split_text("长文测试。" * 2000)
    assert all(len(c.encode("utf-8")) <= 6000 for c in chunks)
    assert "".join(chunks) == "长文测试。" * 2000
    print(f"长文本分片: {len(chunks)} 片, 拼接无损 ✓")


if __name__ == "__main__":
    asyncio.run(main())
