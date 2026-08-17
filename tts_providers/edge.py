"""Edge TTS Provider —— 基于微软 Edge 浏览器在线 TTS（免费，无需 API key）。

设计要点：
- rate / volume 必须是带正负号的百分比字符串（如 "+50%"），pitch 是 "+10Hz"；
  故 slider 的数值经 ParamSpec.format_value 转换后再传入。
- 输出固定为 MP3（24kHz / 48kbps / mono），无法在库内切换格式。
- 合成基于 stream() 增量写文件，并通过已写字节估算进度。
"""
from __future__ import annotations

from typing import Callable, List, Optional

import edge_tts

from .base import ParamSpec, TTSProvider, Voice

# edge_tts 固定比特率 48kbps（字节/秒）
_BYTES_PER_SECOND = 48000 // 8
# 朗读速度粗估（加权字/秒），仅用于进度条估算：中文明显慢于拉丁文
_ZH_CHARS_PER_SECOND = 4.5
_DEFAULT_CHARS_PER_SECOND = 14.0


def _weighted_chars(text: str) -> float:
    """CJK 字符按 1 计，其他按 0.25 计，让混合文本的时长估算更准。"""
    return sum(1.0 if ord(c) > 0x2E80 else 0.25 for c in text)


class EdgeTTSProvider(TTSProvider):
    id = "edge"
    name = "Edge TTS (微软 · 免费)"
    requires_network = True
    requires_api_key = False

    async def list_voices(self) -> List[Voice]:
        voices = await edge_tts.list_voices()
        result: List[Voice] = []
        for v in voices:
            short = v.get("ShortName", "")
            if not short:
                continue
            locale = v.get("Locale", "")
            gender = v.get("Gender", "")
            language = locale.split("-")[0] if locale else ""
            # 显示名不做任何加工，音源返回什么就显示什么，
            # 保证接入其他 TTS 引擎时无需维护映射
            result.append(
                Voice(
                    id=short,
                    display_name=short,
                    gender=gender,
                    locale=locale,
                    language=language,
                    extra={
                        "friendly": v.get("FriendlyName", short),
                        "status": v.get("Status", ""),
                        "tags": v.get("VoiceTag", {}),
                    },
                )
            )
        # 中文优先排序，便于默认定位
        result.sort(key=lambda x: (x.language != "zh", x.locale, x.id))
        return result

    def supported_formats(self) -> List[str]:
        return ["mp3"]

    def configurable_params(self) -> List[ParamSpec]:
        return [
            ParamSpec(
                "rate", "语速", "slider", default=0,
                min=-50, max=200, step=10, fmt="{:+d}%",
                help="正数加快，负数减慢（百分比）",
            ),
            ParamSpec(
                "volume", "音量", "slider", default=0,
                min=-100, max=100, step=10, fmt="{:+d}%",
                help="正数增大，负数减小（百分比）",
            ),
            ParamSpec(
                "pitch", "音调", "slider", default=0,
                min=-50, max=50, step=5, fmt="{:+d}Hz",
                help="正数升高，负数降低（赫兹）",
            ),
        ]

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        params: dict,
        out_path: str,
        progress_cb: Optional[Callable] = None,
    ) -> None:
        rate = params.get("rate", "+0%")
        volume = params.get("volume", "+0%")
        pitch = params.get("pitch", "+0Hz")

        # 估算总字节（仅用于进度条）：按声音语言选择朗读速度
        is_zh = voice_id.split("-")[0].lower() == "zh"
        chars_per_sec = _ZH_CHARS_PER_SECOND if is_zh else _DEFAULT_CHARS_PER_SECOND
        est_seconds = max(1.0, _weighted_chars(text) / chars_per_sec)
        est_total = int(est_seconds * _BYTES_PER_SECOND)

        comm = edge_tts.Communicate(
            text, voice_id, rate=rate, volume=volume, pitch=pitch
        )
        written = 0
        with open(out_path, "wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                    written += len(chunk["data"])
                    if progress_cb:
                        # 比特率固定，已写字节数可精确换算为已生成时长
                        progress_cb(written, est_total, written / _BYTES_PER_SECOND)
