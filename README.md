# EchoSRT 🎬 v0.9.1

基于 `faster-whisper` 与 `LLM大模型` 的现代化本地视频字幕自动化工作站。

## 核心特性
- **异步流水线 (Async Pipeline)**：底层重构为独立的后台 Worker 车间，实现多任务排队、无阻塞并发流转。
- **一站式 AI 工作流**：集成了视频抽音、双引擎语音识别与大语言模型 (LLM) 智能翻译，支持从生肉视频直出完美熟肉多语言字幕。
- **WebUI交互**：基于 Vue 3 构建，提供全局任务监视器、实时逐句滚动日志及高阶参数配置。
- **历史资产与看板管理**：支持勾选批量下发流水线任务、回溯中断工作流、下载历史产物及清空释放磁盘空间。
- **双引擎 ASR 识别**：
  - *本地 GPU 引擎*：基于 `faster-whisper`，自动探测 Nvidia 显卡并启用加速（支持 Mac CPU 平滑回退），支持 VAD 静音过滤、幻觉抑制等高级解码参数。
  - *云端 API 引擎*：兼容标准的 OpenAI Audio API 及第三方代理，支持超大音频 (25MB+) 自动无损切片推流，并支持说话人识别与词级时间戳等高阶特性。

## 环境准备

- Python >= 3.8
- FFmpeg 
  - *Windows*：可直接将 `ffmpeg.exe` 放入项目的 `bin/ffmpeg/bin/` 目录下。
  - *Mac/Linux*：请通过包管理器全局安装（如 `brew install ffmpeg` 或 `sudo apt install ffmpeg`）。

- **NVIDIA GPU 加速环境 (可选但强烈推荐)**
  - 需要安装相应的 **NVIDIA 显卡驱动**。
  - 需配置 **CUDA Toolkit** (推荐 11.x 或 12.x) 及对应的 **cuDNN** 库，以便底层 `CTranslate2` 引擎能正常调用 GPU 算力。
  - *注：程序会自动探测系统环境。若未检测到 Nvidia 显卡或 CUDA 环境不完整，将平滑回退至纯 CPU 模式运行（Mac 设备也会自动使用 CPU），但处理速度会显著下降。*

## 使用方法

### 🐳 方式一：Docker 部署

我们通过 GitHub Actions 提供了全自动构建的官方预编译镜像（托管于 GHCR），支持纯 CPU 与 NVIDIA GPU 硬件加速。**强烈推荐直接拉取预编译镜像**，以避免本地由于网络波动或环境问题导致的构建失败。

**✨ 推荐：直接拉取云端预编译镜像**
在项目根目录下直接执行以下命令，即可一键拉取成品镜像并启动服务：

```bash
# 启动轻量级 CPU 版 (适合无显卡 NAS 或纯调用云端 API 的用户)
docker-compose up -d echosrt-cpu

# 启动满血 GPU 版 (需物理机配有 Nvidia 显卡并安装了 Container Toolkit)
docker-compose up -d echosrt-gpu
```
启动后，浏览器访问 `http://[IP]:8000` 即可进入工作台。

🛠️ 备选：本地自行构建 +如果你想修改源码进行二次开发或定制 Docker 环境，请打开 docker-compose.yml，注释掉 image: 配置行并取消 build: 块的注释。然后执行 docker-compose up -d --build 进行构建。 启动后，浏览器访问 http://127.0.0.1:8000 即可进入工作台。

### 🐍 方式二：本地 Python 源码部署 (极客/开发者)

1. **安装运行依赖**
建议通过项目根目录下的 `requirements.txt` 一键安装所有必备依赖（包含视频提取、语音识别以及 LLM 翻译所需的核心库）：
```bash
pip install -r requirements.txt
```

2. **一键启动 WebUI**
   - 在项目根目录下，使用 Python 运行跨平台统一启动脚本：
     ```bash
     python app.py
     ```

脚本会自动启动后端 API 及静态页面托管，浏览器访问 `http://127.0.0.1:8000` 即可进入工作台；访问 `http://127.0.0.1:8000/docs` 可查看二次开发 API 接口文档。

> 💡 **保留的 CLI 命令行模式**：依然可以在终端直接运行 `python main.py` 在命令行提取字幕（首次运行会自动初始化配置文件）。

## TODO

- [x] **分流代理控制**：云端识别API和LLM 翻译API可独立选择是否使用全局代理，实现接入不同地区云端模型时分流代理。（v0.9.2更新）
- [ ] **任务队列进度**：“全局队列面板”中直接显示具体的进度百分比/子状态。
- [ ] **LLM翻译断点续传**：LLM翻译模块增加“断点续传/缓存”机制。
- [ ] **空间管理优化**：提供“清理中间产物（如保留 SRT，删除 video 和 wav）”的配置选项，工作区面板显示每个任务及总任务占用的空间大小。
- [ ] **WebSocket断线重连**：加入 WebSocket 的断线自动重连机制（结合轮询 /api/task/status 作为兜底），以确保长任务的状态同步。
- [ ] **模型下载进度显示优化**：优化模型下载量的动态显示。
