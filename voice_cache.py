"""声音列表本地缓存，避免每次启动都联网拉取。

缓存文件位于 ~/.tts_studio/voices_cache.json，按 provider_id 分别存储，
默认 7 天过期；界面提供"刷新"按钮强制重新拉取。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List

from tts_providers.base import Voice
from config import CONFIG_DIR

CACHE_FILE = CONFIG_DIR / "voices_cache.json"
CACHE_TTL = 7 * 24 * 3600  # 7 天
CACHE_VERSION = 3  # 显示名格式变更时递增，旧缓存自动作废


def _voice_to_dict(v: Voice) -> dict:
    return {
        "id": v.id,
        "display_name": v.display_name,
        "gender": v.gender,
        "locale": v.locale,
        "language": v.language,
        "extra": v.extra,
    }


def _dict_to_voice(d: dict) -> Voice:
    return Voice(
        id=d["id"],
        display_name=d["display_name"],
        gender=d.get("gender", ""),
        locale=d.get("locale", ""),
        language=d.get("language", ""),
        extra=d.get("extra", {}),
    )


def load_cache(provider_id: str) -> List[Voice]:
    """读取某 provider 的缓存声音；不存在或过期返回空列表。"""
    if not CACHE_FILE.exists():
        return []
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    entry = data.get(provider_id)
    if not entry:
        return []
    if entry.get("v") != CACHE_VERSION:
        return []
    if time.time() - entry.get("ts", 0) > CACHE_TTL:
        return []
    return [_dict_to_voice(v) for v in entry.get("voices", [])]


def save_cache(provider_id: str, voices: List[Voice]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {}
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[provider_id] = {
        "v": CACHE_VERSION,
        "ts": time.time(),
        "voices": [_voice_to_dict(v) for v in voices],
    }
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
