"""TTS Studio —— 跨平台可视化 TTS 桌面应用（Flet）。

界面与引擎解耦：
- 引擎通过 tts_providers 注册，切换/新增引擎不改界面。
- 声音与参数控件均由 provider 动态驱动。
- 合成在后台协程跑，进度条实时更新，完成后显示时长/大小。

视觉原则（单屏、不滚动、黑白灰）：
- 左侧文本输入为主体，右侧为紧凑设置栏，底部为操作条。
- 无强调色：灰阶种子生成黑白灰配色，支持 浅色/深色/跟随系统。
- 控件用 hint_text 代替浮动 label，行高更矮、右栏更紧凑。
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import flet as ft

from config import load_config, save_config
from voice_cache import load_cache, save_cache
from tts_providers import list_providers, get_provider, default_provider_id
from tts_providers.base import CredentialSpec, ParamSpec, Voice

GRAY_SEED = "#616161"  # 中性灰种子，Material 从它生成的整套色板都是黑白灰
RADIUS = 8
RAIL_WIDTH = 300
HAIRLINE = ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)
LABEL_W = 36  # 右栏设置行的标签列宽，所有行对齐

THEME_OPTIONS = [("system", "跟随系统"), ("light", "浅色"), ("dark", "深色")]
THEME_MODES = {"light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}


def flat_field(**kwargs) -> ft.TextField:
    """完全平面化的输入框：无边框、无底色。"""
    kwargs.setdefault("dense", True)
    kwargs.setdefault("text_size", 13)
    kwargs.setdefault("border", ft.InputBorder.NONE)
    kwargs.setdefault("fill_color", ft.Colors.TRANSPARENT)
    kwargs.setdefault("content_padding", ft.padding.only(left=2, right=2))
    return ft.TextField(**kwargs)


class FlatSelect(ft.Container):
    """纯文字下拉：无边框无箭头，点文字弹菜单，当前项打勾，悬停微亮。"""

    def __init__(self, options=None, value=None, hint="", on_change=None,
                 expand=False, width=None, text_size=13):
        self._hint = hint
        self._on_change = on_change
        self._options: List[Tuple[str, str]] = []
        self._items: List[Tuple[str, ft.PopupMenuItem]] = []
        self.value = value
        self._text = ft.Text(size=text_size, max_lines=1,
                             overflow=ft.TextOverflow.ELLIPSIS)
        self._menu = ft.PopupMenuButton(
            content=ft.Container(content=self._text,
                                 padding=ft.padding.symmetric(6, 4)),
            items=[])
        super().__init__(content=self._menu, expand=expand, width=width,
                         border_radius=6, on_hover=self._on_hover)
        self.set_options(options or [], value)

    def _on_hover(self, e):
        self.bgcolor = (ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE)
                        if e.data == "true" else None)
        self.update()

    def set_options(self, options: List[Tuple[str, str]], value):
        """options 为 (key, 显示文字) 列表；value 为当前选中的 key。"""
        self._options = list(options)
        keys = [k for k, _ in self._options]
        self.value = value if value in keys else (keys[0] if keys else None)
        self._items = []
        for key, label in self._options:
            item = ft.PopupMenuItem(
                text=label, height=34, checked=(key == self.value),
                on_click=lambda e, k=key: self._pick(k))
            self._items.append((key, item))
        self._menu.items = [item for _, item in self._items]
        self._refresh()

    def _pick(self, key):
        self.value = key
        self._refresh()
        if self._on_change:
            self._on_change(None)

    def _refresh(self):
        labels = dict(self._options)
        if self.value is not None and self.value in labels:
            self._text.value = labels[self.value]
            self._text.color = None
        else:
            self._text.value = self._hint
            self._text.color = ft.Colors.ON_SURFACE_VARIANT
        for key, item in self._items:
            item.checked = (key == self.value)
        if self.page:  # 未挂载到页面前不能 update
            self.update()


def lbl(text: str) -> ft.Text:
    """设置行的左对齐小标签。"""
    return ft.Text(text, size=12, width=LABEL_W,
                   color=ft.Colors.ON_SURFACE_VARIANT)


def short_path(path: str, limit: int = 30) -> str:
    """长路径只显示尾部（目录名比前缀更有信息量）。"""
    return path if len(path) <= limit else "…" + path[-limit:]

LANG_NAMES = {
    "zh": "中文", "en": "英语", "ja": "日语", "ko": "韩语", "fr": "法语",
    "de": "德语", "es": "西班牙语", "ru": "俄语", "pt": "葡萄牙语",
    "it": "意大利语", "ar": "阿拉伯语", "hi": "印地语", "th": "泰语",
    "vi": "越南语", "id": "印尼语", "nl": "荷兰语", "tr": "土耳其语",
    "pl": "波兰语", "sv": "瑞典语", "da": "丹麦语", "fi": "芬兰语",
}


def log(msg: str):
    # flet run 只转发子进程 stderr，日志统一走 stderr
    print(msg, file=sys.stderr, flush=True)


def fmt_duration(sec: float) -> str:
    return str(timedelta(seconds=int(sec)))


def lang_label(code: str) -> str:
    return LANG_NAMES.get(code, code) if code else "全部"


class TTSStudioApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.config = load_config()
        self.providers = list_providers()
        self.all_voices: List[Voice] = []
        self._param_widgets: Dict[str, Tuple[ft.Slider, ft.Text]] = {}
        self._param_selects: Dict[str, "FlatSelect"] = {}
        self._busy = False
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self):
        page = self.page
        page.title = "TTS Studio"
        self._apply_theme()
        page.window.width = 960
        page.window.height = 640
        page.padding = 0

        # —— 顶栏：应用名 + 主题/引擎选择 ——
        self.theme_dd = FlatSelect(
            options=THEME_OPTIONS, value=self.config.get("theme", "system"),
            on_change=self._on_theme_change, width=86)

        self.provider_dd = FlatSelect(
            options=[(p.id, p.name) for p in self.providers],
            value=self.config.get("provider") or default_provider_id(),
            on_change=self._on_provider_change, width=210)

        topbar = ft.Container(
            padding=ft.padding.symmetric(10, 16),
            border=ft.border.only(bottom=HAIRLINE),
            content=ft.Row(
                [ft.Text("TTS Studio", size=14, weight=ft.FontWeight.BOLD),
                 ft.Row([self.theme_dd, self.provider_dd], spacing=8)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN))

        # —— 右侧设置栏：标签列 + 控件的设置行，无框无底色 ——
        self.lang_dd = FlatSelect(
            hint="语言", on_change=self._on_filter_change, expand=True)
        self.gender_dd = FlatSelect(
            hint="性别", on_change=self._on_filter_change, width=70)
        self.voice_dd = FlatSelect(
            hint="声音", on_change=self._on_voice_change, expand=True)
        self.refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH, icon_size=15,
            tooltip="联网刷新声音列表", on_click=self._on_refresh_voices)

        self.param_col = ft.Column(spacing=2)
        # 引擎凭据（如讯飞 AppID/APIKey/APISecret），按引擎声明动态生成
        self.cred_section = ft.Column(spacing=2)

        # 输出目录：可点击的文字行，长路径只露尾部，悬停可见全路径
        out_dir = self.config.get("output_dir", "") or str(Path.home())
        self._out_dir = out_dir
        self.dir_text = ft.Text(
            short_path(out_dir), size=12, expand=True,
            overflow=ft.TextOverflow.ELLIPSIS, tooltip=out_dir)
        self.dir_row = ft.Container(
            expand=True, ink=True, border_radius=6,
            on_click=self._on_pick_dir,
            padding=ft.padding.symmetric(0, 2),
            content=ft.Row(spacing=6, controls=[
                ft.Icon(ft.Icons.FOLDER_OPEN, size=14,
                        color=ft.Colors.ON_SURFACE_VARIANT),
                self.dir_text,
            ]))
        self.filename_tf = flat_field(
            hint_text="文件名", value=self.config.get("filename", "output.mp3"),
            expand=True, text_size=12)

        # macOS 上 flet 0.28.3 的 FilePicker 对话框静默失败（flet#5334），
        # 改用系统原生目录选择；其他平台仍走 FilePicker。
        self.dir_picker = ft.FilePicker(on_result=self._on_dir_picked)
        page.overlay.append(self.dir_picker)

        rail = ft.Container(
            width=RAIL_WIDTH,
            padding=ft.padding.symmetric(12, 16),
            border=ft.border.only(left=HAIRLINE),
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO, spacing=6,
                controls=[
                    ft.Row([lbl("语言"), self.lang_dd, lbl("性别"),
                            self.gender_dd], spacing=6),
                    ft.Row([lbl("声音"), self.voice_dd, self.refresh_btn],
                           spacing=2),
                    ft.Divider(height=1),
                    self.param_col,
                    self.cred_section,
                    ft.Divider(height=1),
                    ft.Row([lbl("目录"), self.dir_row], spacing=6),
                    ft.Row([lbl("文件"), self.filename_tf], spacing=6),
                ]))

        # —— 左侧：文本输入（主体） ——
        self.text_tf = ft.TextField(
            hint_text="粘贴或输入要朗读的文本", multiline=True, min_lines=8,
            border=ft.InputBorder.NONE, border_radius=RADIUS, dense=True,
            fill_color=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
            content_padding=ft.padding.symmetric(12, 14))
        editor = ft.Container(
            expand=True, padding=ft.padding.symmetric(12, 16),
            content=ft.Column(spacing=0, expand=True, controls=[self.text_tf]))
        self.text_tf.expand = True

        # —— 底部操作条：主按钮 + 状态 + 进度 ——
        self.synth_btn = ft.FilledButton(
            "生成语音", icon=ft.Icons.PLAY_ARROW_ROUNDED,
            height=38, on_click=self._on_synthesize)
        self.progress = ft.ProgressBar(value=0, bar_height=4, visible=False)
        self.status = ft.Text("准备就绪", size=12, max_lines=1,
                              overflow=ft.TextOverflow.ELLIPSIS)
        # 进度条外包一层固定高度容器，隐藏时不引起布局跳动
        progress_slot = ft.Container(height=4, content=self.progress)
        bottombar = ft.Container(
            padding=ft.padding.symmetric(10, 16),
            border=ft.border.only(top=HAIRLINE),
            content=ft.Row(
                [self.synth_btn,
                 ft.Column(expand=True, spacing=5,
                           alignment=ft.MainAxisAlignment.CENTER,
                           controls=[self.status, progress_slot])],
                spacing=14))

        page.add(ft.Column(
            expand=True, spacing=0,
            controls=[
                topbar,
                ft.Row(expand=True, spacing=0,
                       vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                       controls=[editor, rail]),
                bottombar,
            ]))

        self._init_provider_ui()
        self._load_voices(use_cache=True)
        log("[BUILD] 完成")

    # ------------------------------------------------------------- 主题
    def _apply_theme(self):
        t = ft.Theme(color_scheme_seed=GRAY_SEED)
        # 浅色/深色共用同一套灰阶色板，由 theme_mode 决定表面色
        self.page.theme = t
        self.page.dark_theme = t
        mode = self.config.get("theme", "system")
        self.page.theme_mode = THEME_MODES.get(mode, ft.ThemeMode.SYSTEM)

    def _on_theme_change(self, e):
        self.config["theme"] = self.theme_dd.value
        save_config(self.config)
        self._apply_theme()
        self.page.update()

    # ----------------------------------------------------- provider / 参数
    def _current_provider(self):
        return get_provider(self.provider_dd.value)

    def _init_provider_ui(self):
        p = self._current_provider()
        self._param_widgets.clear()
        self._param_selects.clear()
        self.param_col.controls.clear()
        for spec in p.configurable_params():
            self._make_param_control(spec)
        self._build_credentials(p)
        self.page.update()

    def _make_param_control(self, spec: ParamSpec):
        saved = self.config.get("params", {}).get(spec.key)
        if spec.type == "dropdown":
            opts = [(str(o.get("value")), str(o.get("label", o.get("value"))))
                    for o in spec.options]
            values = [v for v, _ in opts]
            sel = FlatSelect(
                options=opts, hint=spec.label, expand=True, text_size=13,
                value=saved if saved in values else spec.default)
            self._param_selects[spec.key] = sel
            self.param_col.controls.append(ft.Row(
                [ft.Text(spec.label, size=12, width=LABEL_W,
                         color=ft.Colors.ON_SURFACE_VARIANT), sel],
                spacing=6))
            return
        if spec.type == "slider":
            raw = spec.parse_value(saved) if saved is not None else spec.default
            slider = ft.Slider(
                min=spec.min, max=spec.max,
                divisions=int((spec.max - spec.min) // spec.step),
                label="{value}", value=raw, expand=True)
            valtxt = ft.Text(spec.format_value(raw), width=44, size=11,
                             color=ft.Colors.ON_SURFACE_VARIANT,
                             text_align=ft.TextAlign.RIGHT)
            slider.data = spec.key

            def on_change(e, s=slider, sp=spec, vt=valtxt):
                vt.value = sp.format_value(s.value)
                vt.update()
            slider.on_change = on_change

            self.param_col.controls.append(ft.Row(
                [ft.Text(spec.label, size=12, width=LABEL_W,
                         color=ft.Colors.ON_SURFACE_VARIANT),
                 slider, valtxt],
                spacing=6))
            self._param_widgets[spec.key] = (slider, valtxt)

    def _build_credentials(self, p):
        """按引擎声明的凭据生成配置框；无需凭据的引擎此区为空。"""
        self.cred_section.controls.clear()
        specs = p.credential_specs()
        if not specs:
            return
        saved = self.config.get("credentials", {}).get(p.id, {})
        self.cred_section.controls.append(ft.Divider(height=1))
        for spec in specs:
            field = flat_field(
                hint_text=spec.label, value=saved.get(spec.key, ""),
                password=spec.secret, can_reveal_password=spec.secret,
                text_size=12)
            field.on_change = lambda e, k=spec.key: self._save_credential(k, e)
            self.cred_section.controls.append(field)

    def _save_credential(self, key: str, e: ft.ControlEvent):
        p = self._current_provider()
        creds = self.config.setdefault("credentials", {}).setdefault(p.id, {})
        creds[key] = e.control.value or ""
        save_config(self.config)

    # ---------------------------------------------------------- 声音筛选
    def _rebuild_lang_options(self):
        langs = sorted({v.language for v in self.all_voices if v.language})
        lang_options = [("", "全部")] + [(lg, lang_label(lg)) for lg in langs]
        saved = self.config.get("language_filter", "zh")
        self.lang_dd.set_options(
            lang_options, saved if any(k == saved for k, _ in lang_options) else "")
        self.gender_dd.set_options(
            [("", "全部"), ("Female", "女声"), ("Male", "男声")],
            self.config.get("gender_filter", ""))

    def _apply_filters(self):
        lang = self.lang_dd.value or ""
        gender = self.gender_dd.value or ""
        filtered = [
            v for v in self.all_voices
            if (not lang or v.language == lang)
            and (not gender or v.gender == gender)
        ]
        options = [(v.id, v.display_name) for v in filtered]
        current = self.config.get("voice", "")
        self.voice_dd.set_options(options, current)
        self.page.update()

    def _load_voices(self, use_cache: bool):
        p = self._current_provider()
        log(f"[VOICES] 加载声音 use_cache={use_cache} provider={p.id}")
        if use_cache:
            cached = load_cache(p.id)
            if cached:
                self.all_voices = cached
                self._rebuild_lang_options()
                self._apply_filters()
                self._set_status(f"就绪 · {len(cached)} 个声音")
                log(f"[VOICES] 缓存命中 {len(cached)} 个")
                return
        self._set_status("正在联网获取声音列表…")
        self.page.run_task(self._fetch_voices)

    async def _fetch_voices(self):
        p = self._current_provider()
        try:
            voices = await p.list_voices()
            self.all_voices = voices
            save_cache(p.id, voices)
            self._rebuild_lang_options()
            self._apply_filters()
            self._set_status(f"就绪 · {len(voices)} 个声音")
            log(f"[VOICES] 联网加载 {len(voices)} 个声音")
        except Exception as ex:
            self._set_status(f"获取声音失败：{ex}", error=True)
            log(f"[VOICES] 获取失败: {ex!r}")
        self.page.update()

    # ----------------------------------------------------------- 事件
    def _on_provider_change(self, e):
        self.config["provider"] = self.provider_dd.value
        self.all_voices = []
        self.voice_dd.set_options([], None)
        self._init_provider_ui()
        self.page.update()
        self._load_voices(use_cache=True)

    def _on_filter_change(self, e):
        self.config["language_filter"] = self.lang_dd.value or ""
        self.config["gender_filter"] = self.gender_dd.value or ""
        self._apply_filters()

    def _on_voice_change(self, e):
        if self.voice_dd.value:
            self.config["voice"] = self.voice_dd.value

    def _on_refresh_voices(self, e):
        self._load_voices(use_cache=False)

    # macOS：系统原生目录选择对话框，绕开 flet#5334
    async def _on_pick_dir(self, e):
        if sys.platform != "darwin":
            self.dir_picker.get_directory_path()
            return
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e",
                'POSIX path of (choose folder with prompt "选择输出目录")',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            out, _err = await proc.communicate()
        except FileNotFoundError:
            self.dir_picker.get_directory_path()
            return
        if proc.returncode == 0:
            path = out.decode("utf-8", "replace").strip().rstrip("/")
            if path:
                self._set_out_dir(path)
        # 用户取消（returncode != 0）属于正常操作，静默返回

    def _on_dir_picked(self, e: ft.FilePickerResultEvent):
        if e.path:
            self._set_out_dir(e.path)

    def _set_out_dir(self, path: str):
        self._out_dir = path
        self.config["output_dir"] = path
        self.dir_text.value = short_path(path)
        self.dir_text.tooltip = path
        self.page.update()

    # ----------------------------------------------------------- 合成
    def _gather_params(self) -> dict:
        p = self._current_provider()
        params = {}
        for spec in p.configurable_params():
            if spec.type == "dropdown" and spec.key in self._param_selects:
                params[spec.key] = self._param_selects[spec.key].value
            elif spec.key in self._param_widgets:
                slider, _ = self._param_widgets[spec.key]
                params[spec.key] = spec.format_value(slider.value)
            else:
                params[spec.key] = spec.format_value(spec.default)
        return params

    def _on_synthesize(self, e):
        if self._busy:
            return
        text = (self.text_tf.value or "").strip()
        if not text:
            self._set_status("请先输入要朗读的文本", error=True)
            return
        voice = self.voice_dd.value
        if not voice:
            self._set_status("请选择一个声音", error=True)
            return
        out_dir = getattr(self, "_out_dir", "") or str(Path.home())
        fname = (self.filename_tf.value or "output.mp3").strip()
        if not fname.lower().endswith(".mp3"):
            fname += ".mp3"
        out_path = str(Path(out_dir) / fname)
        params = self._gather_params()

        self.config["params"] = params
        self.config["filename"] = fname
        self.config["output_dir"] = out_dir
        self.config["voice"] = voice
        save_config(self.config)

        self._busy = True
        self.synth_btn.disabled = True
        self.progress.visible = True
        self.progress.value = 0
        self._set_status("合成中…")

        self.page.run_task(self._run_synthesis, text, voice, params, out_path)

    async def _run_synthesis(self, text, voice, params, out_path):
        p = self._current_provider()
        # 注入界面收集的账号凭据（无凭据需求的引擎为空操作）
        p.set_credentials(self.config.get("credentials", {}).get(p.id, {}))
        try:
            def on_progress(written, total, seconds=None):
                frac = (written / total) if total else 0.0
                # 估总量只用于节奏；封顶 95%，完成前绝不显示满格
                self.progress.value = max(0.02, min(0.95, frac))
                if seconds is not None:
                    self.status.value = (
                        f"合成中… {min(frac, 0.95):.0%} · "
                        f"已生成 {fmt_duration(seconds)}")
                else:
                    self.status.value = f"合成中… 已写 {written / 1024:.0f} KB"
                self.page.update()
            await p.synthesize(text, voice, params, out_path,
                               progress_cb=on_progress)

            dur, size_kb = self._inspect_audio(out_path)
            self.progress.value = 1.0
            self.status.value = (
                f"完成 · 时长 {fmt_duration(dur)} · {size_kb / 1024:.1f} MB · "
                f"{out_path}")
            self.status.tooltip = out_path
            self.status.color = None
        except Exception as ex:
            self._set_status(f"合成失败：{ex}", error=True)
            log(f"[SYNTH] 失败: {ex!r}")
        finally:
            self._busy = False
            self.synth_btn.disabled = False
            self.page.update()

    @staticmethod
    def _inspect_audio(out_path: str):
        try:
            from mutagen.mp3 import MP3
            audio = MP3(out_path)
            dur = audio.info.length
        except Exception:
            dur = 0.0
        size_kb = os.path.getsize(out_path) / 1024
        return dur, size_kb

    def _set_status(self, msg: str, error: bool = False):
        self.status.value = msg
        # 全局黑白灰；红色只作为错误语义色
        self.status.color = ft.Colors.ERROR if error else None
        self.page.update()


def main(page: ft.Page):
    TTSStudioApp(page)


if __name__ == "__main__":
    ft.app(main)
