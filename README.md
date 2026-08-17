# TTS Studio

一个**跨平台（macOS / Windows）**的可视化 TTS（文字转语音）桌面应用。
界面基于 [Flet](https://flet.dev)（Flutter 渲染，Material Design），
TTS 引擎**可插拔**——内置两个引擎，换别家只需加一个文件。

## 功能

- **引擎可切换**：TTS 引擎抽象为 Provider，内置 `Edge TTS (微软·免费)` 与 `讯飞在线合成 (每日500次免费)`；加 Azure / 阿里 / 字节等只需实现 `TTSProvider` 子类并注册，界面自动出现新选项与参数。
- **账号凭据可配置**：需要 API Key 的引擎（如讯飞）声明所需凭据后，界面自动出现配置框（密码式输入、可切换明文），按引擎分别保存在本地。
- **声音下拉**：从引擎动态获取（Edge 有 322 个声音、14 个中文），按**语言 / 性别**筛选，本地缓存避免每次联网。
- **参数可调**：参数项由引擎声明、界面动态生成（滑杆 / 下拉），换引擎后参数面板自动对应更换。
- **长文本自动分片**：单次接口有长度限制时（讯飞 8000 字节）自动分段合成再拼接。
- **输出**：选目录、填文件名，合成后显示**时长 / 大小**。
- **记忆设置**：下次打开自动恢复上次的引擎、声音、参数、凭据、输出目录。

## 讯飞引擎配置（免费 500 次/天）

1. 注册 [讯飞开放平台](https://www.xfyun.cn/)，创建应用，在应用详情页拿到 **AppID / APIKey / APISecret**（在线语音合成服务默认每日 500 次免费调用）。
2. 在本应用顶部"引擎"切换到讯飞，右栏会出现三个凭据输入框，填入即可（保存在本机 `~/.tts_studio/config.json`，不会上传）。
3. 发音人以讯飞控制台授权为准；内置 `xiaoyan` 等常用音色，未授权的音色会报 11200，按提示去控制台添加试用即可。

> 踩坑记录：讯飞当前网关（kong）**只接受鉴权信息放在 WebSocket 握手的 HTTP 头**（`Date` + `Authorization`），官方文档 Python demo 的 URL query 传参方式已失效，会返回 401 "HMAC signature does not match"。本项目的对接方式以 `tts_providers/xfyun.py` 实测为准。

## 快速开始

需要 **Python 3.10+**（Flet 0.28 要求）。建议 3.12。

```bash
cd tts_studio
bash run_macos.sh        # macOS（自动建 venv、装依赖、处理证书）
# Windows：双击 run_windows.bat
```

首次运行脚本会自动：创建 `.venv`、安装依赖、用 certifi 证书解决 SSL、启动应用。

> **首次启动会下载 Flet 桌面运行时（约 52MB，来自 GitHub）**，之后缓存在 `~/.flet/`，不再重复下载。

### 如果首次下载卡住（GitHub 受限）

编辑 `run_macos.sh` / `run_windows.bat`，取消代理两行的注释，填你自己的本地代理端口：

```bash
export https_proxy=http://127.0.0.1:7890
export http_proxy=http://127.0.0.1:7890
```

## 目录结构

```
tts_studio/
  main.py                 # Flet 应用入口与界面
  config.py               # 配置读写（~/.tts_studio/config.json）
  voice_cache.py          # 声音列表本地缓存
  tts_providers/
    __init__.py           # 引擎注册表：list_providers() / get_provider()
    base.py               # TTSProvider 抽象基类 + Voice/ParamSpec/CredentialSpec
    edge.py               # Edge TTS 实现（免凭据）
    xfyun.py              # 讯飞在线合成实现（AppID/APIKey/APISecret + WebSocket 签名）
  test_core.py            # 核心功能自测（不依赖 GUI）
  run_macos.sh            # 一键运行（macOS）
  run_windows.bat         # 一键运行（Windows）
  requirements.txt
  pyproject.toml          # flet build 打包配置
  build_macos.sh          # 打包 .app
  build_windows.bat       # 打包 .exe
```

## 核心自测（无需 GUI）

验证 Provider 抽象层与 Edge 引擎是否正常（联网拉声音 + 合成一小段）：

```bash
source .venv/bin/activate
python test_core.py
```

## 打包成原生应用

方式一：在本机打包。

```bash
# macOS（在 Mac 上）
bash build_macos.sh          # 产物：build/macos/TTS Studio.app

# Windows（在 Windows 上）
build_windows.bat            # 产物：build\windows\TTS Studio.exe
```

> 原生应用不交叉编译：macOS 包在 Mac 上打，Windows 包在 Windows 上打。
> 打包同样会用到 Flet 桌面运行时，若下载受限请参照上面的代理设置。

方式二：GitHub Actions 云端打包（**推荐，无需 Windows 机器**）。

仓库已内置 `.github/workflows/release.yml`：推送一个 `v*` 标签（如 `v0.1.0`），
GitHub 会自动在 macOS / Windows 云主机上分别构建安装包并发布到 Release：

```bash
git tag v0.1.0
git push origin v0.1.0
```

也可在仓库 Actions 页面手动触发（只构建不上传，产物在 Artifacts 里下载）。

## 新增 TTS 引擎（示例）

1. 新建 `tts_providers/myprovider.py`，继承 `TTSProvider`，实现
   `list_voices / supported_formats / configurable_params / synthesize`；
   需要账号的引擎再实现 `credential_specs()` 声明所需凭据（AppID、
   APIKey 等），界面会自动生成配置框并在合成前注入。
2. 在 `tts_providers/__init__.py` 注册：

   ```python
   _PROVIDERS = {
       EdgeTTSProvider.id: EdgeTTSProvider(),
       XfyunTTSProvider.id: XfyunTTSProvider(),
       MyProvider.id: MyProvider(),
   }
   ```

3. 界面“引擎”菜单自动出现新选项，声音与参数控件自动生成。**无需改界面代码。**

## 已知限制

- Edge TTS 仅输出 **MP3**（24kHz / 48kbps / mono，库内固定）；讯飞输出 16kHz lame MP3。
- 讯飞发音人列表为内置静态表（官方无列表接口），以控制台实际授权为准。
- 凭据以明文保存在本机 `~/.tts_studio/config.json`，请勿在共享设备上使用。
- 开发环境若为 Apple Silicon 上的 Homebrew Python，可能需要对 Python 二进制重新 ad-hoc 签名（`codesign --force --sign - <Python.framework>/Versions/3.12/Python`）才能运行；脚本不涉及此步，遇到再处理。
