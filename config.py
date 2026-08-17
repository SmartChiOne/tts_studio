"""用户配置读写（记住上次设置）。

配置文件位于 ~/.tts_studio/config.json。
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".tts_studio"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "provider": "edge",
    "voice": "zh-CN-XiaoxiaoNeural",
    "language_filter": "zh",
    "gender_filter": "",
    "params": {"rate": "+0%", "volume": "+0%", "pitch": "+0Hz"},
    "output_dir": str(Path.home()),
    "filename": "output.mp3",
    "theme": "system",
}


def load_config() -> dict:
    """读取配置，与默认值合并，保证字段齐全。"""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            merged = dict(DEFAULT_CONFIG)
            merged.update(data)
            return merged
        except Exception:
            return dict(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
