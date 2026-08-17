"""讯飞在线语音合成 Provider（WebSocket 接口，每日 500 次免费）。

设计要点：
- 鉴权：AppID + APIKey + APISecret 三段凭据，按官方算法生成带签名的
  wss URL（hmac-sha256 拼接 host/date/request-line）。
- 输出 MP3：business.aue="lame" 且 sfl=1，流式返回 base64 分片。
- 长文本：单次调用上限 8000 字节，先按段落再按字符切成多个分片，
  逐片合成后顺序拼接（MP3 帧可直接连接）。
- 声音：官方无音色列表接口，内置常用发音人；实际可用性以控制台
  授权为准（未授权报 11200，错误信息会提示）。
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import ssl
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Callable, List, Optional

import websockets
from websockets.exceptions import InvalidStatus

from .base import (CredentialSpec, ParamSpec, TTSProvider, Voice)

_HOST = "tts-api.xfyun.cn"
_PATH = "/v2/tts"

# 单次调用文本上限 8000 字节（utf-8），留余量
_CHUNK_LIMIT = 6000

# 进度估算：中文约 4.5 字/秒，16kHz lame 约 24kbps ≈ 3000 B/s
_CHARS_PER_SECOND = 4.5
_BYTES_PER_SECOND = 3000

# 常用发音人（display_name 用原始 vcn 值；可用性以控制台授权为准）
_VOICES = [
    ("xiaoyan", "Female", "zh-CN", "zh"),
    ("aisjiuxu", "Male", "zh-CN", "zh"),
    ("aisxping", "Female", "zh-CN", "zh"),
    ("aisxyan", "Female", "zh-CN", "zh"),
    ("aisjng", "Female", "zh-CN", "zh"),
]

# 常见错误码的友好提示
_ERROR_HINTS = {
    "10005": "app_id 未授权（检查讯飞控制台的应用信息）",
    "10165": "app_id 与发音人资源不匹配",
    "10313": "app_id 不正确",
    "10163": "鉴权参数错误（检查 APIKey / APISecret）",
    "11200": "该发音人未授权（去讯飞控制台添加试用此发音人）",
    "11201": "今日免费次数已用完（每日 500 次）",
    "11202": "并发超限，请稍后再试",
    "10800": "连接超时，请重试",
    "10166": "文本参数错误",
    "10043": "文本编码错误",
}


def _weighted_chars(text: str) -> float:
    return sum(1.0 if ord(c) > 0x2E80 else 0.25 for c in text)


def _certifi_where() -> Optional[str]:
    """返回 certifi 的 CA 证书路径（未安装则返回 None，走系统证书）。"""
    try:
        import certifi
        return certifi.where()
    except ImportError:
        return None


def split_text(text: str, limit: int = _CHUNK_LIMIT) -> List[str]:
    """长文本分片：先按段落合并，超限再按字符硬切，保证每片 utf-8 字节数不超限。"""
    chunks: List[str] = []
    buf = ""
    for para in text.split("\n"):
        candidate = f"{buf}\n{para}" if buf else para
        if len(candidate.encode("utf-8")) <= limit:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        if len(para.encode("utf-8")) <= limit:
            buf = para
            continue
        sent = ""
        for ch in para:
            if len((sent + ch).encode("utf-8")) > limit:
                chunks.append(sent)
                sent = ch
            else:
                sent += ch
        buf = sent
    if buf:
        chunks.append(buf)
    return [c for c in chunks if c.strip()]


class XfyunTTSProvider(TTSProvider):
    id = "xfyun"
    name = "讯飞在线合成 (每日500次免费)"
    requires_network = True
    requires_api_key = True

    def __init__(self):
        self._creds: dict = {}

    # ----------------------------------------------------------- 凭据
    def credential_specs(self) -> List[CredentialSpec]:
        return [
            CredentialSpec("app_id", "AppID（讯飞控制台的应用ID）"),
            CredentialSpec("api_key", "APIKey", secret=True),
            CredentialSpec("api_secret", "APISecret", secret=True),
        ]

    def set_credentials(self, creds: dict) -> None:
        self._creds = creds or {}

    def _check_creds(self):
        for spec in self.credential_specs():
            if not (self._creds.get(spec.key) or "").strip():
                name = spec.label.split("（")[0].split("(")[0]
                raise RuntimeError(
                    f"请先在右栏填写讯飞 {name}"
                    "（在讯飞开放平台的应用详情页获取）")

    # ----------------------------------------------------------- 能力声明
    async def list_voices(self) -> List[Voice]:
        # 官方无音色列表接口，返回内置常用发音人（原样显示 vcn 值）
        return [
            Voice(id=vcn, display_name=vcn, gender=gender,
                  locale=locale, language=language)
            for vcn, gender, locale, language in _VOICES
        ]

    def supported_formats(self) -> List[str]:
        return ["mp3"]

    def configurable_params(self) -> List[ParamSpec]:
        return [
            ParamSpec("speed", "语速", "slider", default=50,
                      min=0, max=100, step=5, fmt="{:d}"),
            ParamSpec("volume", "音量", "slider", default=50,
                      min=0, max=100, step=5, fmt="{:d}"),
            ParamSpec("pitch", "音调", "slider", default=50,
                      min=0, max=100, step=5, fmt="{:d}"),
        ]

    # ----------------------------------------------------------- 鉴权
    def _auth_headers(self) -> dict:
        """按官方算法生成握手鉴权头（凭据走 HTTP 头，实测当前网关已不接受 query 传参）。"""
        date = format_datetime(datetime.now(timezone.utc), usegmt=True)
        origin = f"host: {_HOST}\ndate: {date}\nGET {_PATH} HTTP/1.1"
        signature = base64.b64encode(hmac.new(
            self._creds["api_secret"].encode(), origin.encode(),
            hashlib.sha256).digest()).decode()
        authorization = (
            f'api_key="{self._creds["api_key"]}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"')
        return {"Date": date, "Authorization": authorization}

    # ----------------------------------------------------------- 合成
    async def synthesize(
        self,
        text: str,
        voice_id: str,
        params: dict,
        out_path: str,
        progress_cb: Optional[Callable] = None,
    ) -> None:
        self._check_creds()
        chunks = split_text(text)
        est_total = int(_weighted_chars(text) / _CHARS_PER_SECOND
                        * _BYTES_PER_SECOND)
        written = 0
        with open(out_path, "wb") as f:
            for i, chunk in enumerate(chunks):
                audio = await self._synth_once(chunk, voice_id, params)
                f.write(audio)
                written += len(audio)
                if progress_cb:
                    progress_cb(written, est_total)
        if progress_cb and len(chunks) > 1:
            progress_cb(written, written)  # 收尾：让界面走完成态

    async def _synth_once(self, text: str, vcn: str, params: dict) -> bytes:
        payload = {
            "common": {"app_id": self._creds["app_id"]},
            "business": {
                "aue": "lame", "sfl": 1, "vcn": vcn, "tte": "UTF8",
                "speed": int(str(params.get("speed", 50)).lstrip("+") or 50),
                "volume": int(str(params.get("volume", 50)).lstrip("+") or 50),
                "pitch": int(str(params.get("pitch", 50)).lstrip("+") or 50),
            },
            "data": {
                "status": 2,
                "text": base64.b64encode(text.encode("utf-8")).decode(),
            },
        }
        try:
            ws = await self._connect()
        except InvalidStatus as ex:
            code = getattr(getattr(ex, "response", None), "status_code", None)
            if code in (401, 403):
                raise RuntimeError(
                    f"讯飞鉴权被拒（HTTP {code}）：请核对三项凭据是否来自同一个应用的"
                    "「WebAPI 接口」栏（APIKey 与 APISecret 必须配对），"
                    "并确认已开通「在线语音合成」服务")
            raise RuntimeError(f"讯飞拒绝连接（HTTP {code}）")
        except ssl.SSLCertVerificationError:
            raise RuntimeError("SSL 证书校验失败（Homebrew Python 缺根证书：pip install certifi）")
        try:
            async with ws:
                await ws.send(json.dumps(payload))
                buf = bytearray()
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    data = json.loads(msg)
                    code = data.get("code")
                    if code != 0:
                        hint = _ERROR_HINTS.get(str(code), "")
                        raise RuntimeError(
                            f"讯飞返回错误 {code}: {data.get('message', '')}"
                            + (f"（{hint}）" if hint else ""))
                    d = data.get("data") or {}
                    if d.get("audio"):
                        buf += base64.b64decode(d["audio"])
                    if d.get("status") == 2:
                        break
                return bytes(buf)
        except asyncio.TimeoutError:
            raise RuntimeError("讯飞接口响应超时，请重试")

    async def _connect(self):
        """连接讯飞 WebSocket。

        - 鉴权凭据走握手请求头（Date + Authorization），实测讯飞当前
          网关（kong）不接受官方旧 demo 的 query 传参方式。
        - 讯飞是国内直连服务，优先绕开系统代理（Clash 等工具的 SOCKS
          系统代理会被 websockets 自动启用，反而连不上且触发
          python-socks 缺失错误）；直连失败再尝试系统代理兜底。
        - 显式用 certifi 根证书，规避 Homebrew Python 无系统 CA 的问题。
        """
        try:
            ctx = ssl.create_default_context(cafile=_certifi_where())
        except Exception:
            ctx = None
        url = f"wss://{_HOST}{_PATH}"
        headers = self._auth_headers()
        try:
            return await websockets.connect(
                url, additional_headers=headers, max_size=None,
                proxy=None, ssl=ctx)
        except OSError:
            try:
                return await websockets.connect(
                    url, additional_headers=headers, max_size=None, ssl=ctx)
            except ImportError:
                raise RuntimeError(
                    "直连失败且系统配置了 SOCKS 代理但缺少 python-socks："
                    "pip install python-socks，或暂时关闭系统代理后重试")
