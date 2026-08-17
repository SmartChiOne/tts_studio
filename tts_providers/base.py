"""TTS Provider 抽象基类与数据结构。

所有 TTS 厂商实现同一套 :class:`TTSProvider` 接口，界面只调用统一接口，
新增厂商只需继承并实现，无需改动界面。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

__all__ = ["Voice", "ParamSpec", "CredentialSpec", "TTSProvider"]


@dataclass
class Voice:
    """单个声音的描述。"""

    id: str            # 传给 synthesize 的标识，如 "zh-CN-XiaoxiaoNeural"
    display_name: str  # UI 显示名
    gender: str = ""   # "Female" / "Male" / ""
    locale: str = ""   # "zh-CN"
    language: str = ""  # "zh"（locale 主语言部分）
    extra: dict = field(default_factory=dict)


@dataclass
class ParamSpec:
    """一个可配置参数的声明，用于驱动 UI 控件动态生成。"""

    key: str                          # 参数键，如 "rate"
    label: str                        # UI 标签，如 "语速"
    type: str = "slider"             # "slider" | "dropdown" | "text"
    default: Any = 0                 # 默认原始值（数值或字符串）
    options: list = field(default_factory=list)   # dropdown 选项 [{"label","value"}]
    min: float = 0                   # slider 最小值
    max: float = 100                 # slider 最大值
    step: float = 1                  # slider 步长
    fmt: str = "{:+d}%"              # 原始值 -> provider 字符串的格式模板
    help: str = ""                   # 说明文字

    def format_value(self, raw: Any) -> str:
        """把 slider 数值按 fmt 渲染成 provider 需要的字符串。"""
        try:
            return self.fmt.format(int(raw))
        except Exception:
            return str(raw)

    def parse_value(self, text: str) -> Any:
        """从已存字符串反解出 slider 数值。"""
        if self.type != "slider":
            return text
        cleaned = str(text).replace("%", "").replace("Hz", "").strip()
        try:
            return int(float(cleaned))
        except Exception:
            return self.default


@dataclass
class CredentialSpec:
    """一项账号凭据的声明（如 AppID / APIKey），驱动 UI 动态生成配置框。"""

    key: str              # 存储键，如 "app_id"
    label: str            # UI 提示文字，如 "AppID"
    secret: bool = False  # True 时密码式显示（可切换明文）
    help: str = ""        # 获取方式的说明链接等


class TTSProvider(ABC):
    """TTS 能力的统一抽象。"""

    name: str = "Base Provider"   # 显示名（带厂商/是否免费等说明）
    id: str = "base"              # provider 唯一 id（用于配置存取）
    requires_network: bool = True
    requires_api_key: bool = False

    @abstractmethod
    async def list_voices(self) -> List[Voice]:
        """返回该厂商支持的全部声音（未筛选）。"""

    @abstractmethod
    def supported_formats(self) -> List[str]:
        """支持的输出格式，如 ["mp3"]。"""

    @abstractmethod
    def configurable_params(self) -> List[ParamSpec]:
        """可配置参数声明，UI 据此动态生成控件。"""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice_id: str,
        params: dict,
        out_path: str,
        progress_cb: Optional[Callable] = None,
    ) -> None:
        """合成语音并写入 out_path。

        progress_cb(written_bytes, estimated_total_bytes, seconds_so_far)
        为可选进度回调：total 仅为估算，不要求精确；seconds 为已生成
        音频时长（若引擎可知），供界面展示。
        """

    def credential_specs(self) -> List[CredentialSpec]:
        """声明本引擎需要的账号凭据（AppID/APIKey 等），UI 据此生成配置框。"""
        return []

    def set_credentials(self, creds: dict) -> None:
        """在合成前注入界面收集到的凭据（key 同 credential_specs）。默认空实现。"""
        return None
