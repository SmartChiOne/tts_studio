"""TTS Provider 注册表。

新增厂商：实现一个 TTSProvider 子类（参考 edge.py），然后把实例加入 _PROVIDERS。
界面会自动出现新选项及其参数控件，无需改动 UI 代码。
"""
from __future__ import annotations

from typing import Dict, List

from .base import TTSProvider
from .edge import EdgeTTSProvider
from .xfyun import XfyunTTSProvider

# 已注册的 provider 实例。新增厂商在这里登记即可。
_PROVIDERS: Dict[str, TTSProvider] = {
    EdgeTTSProvider.id: EdgeTTSProvider(),
    XfyunTTSProvider.id: XfyunTTSProvider(),
}


def list_providers() -> List[TTSProvider]:
    """返回全部已注册 provider。"""
    return list(_PROVIDERS.values())


def get_provider(provider_id: str) -> TTSProvider:
    """按 id 取 provider，找不到抛 KeyError。"""
    if provider_id not in _PROVIDERS:
        raise KeyError(f"未知 TTS 引擎: {provider_id}")
    return _PROVIDERS[provider_id]


def default_provider_id() -> str:
    return list(_PROVIDERS.keys())[0]
