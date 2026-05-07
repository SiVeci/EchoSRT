<div align="center">
  <img src="frontend/logo.png" alt="EchoSRT Logo" width="180">
  <h1>EchoSRT 字幕工作台</h1>
  <p>
    <img src="https://img.shields.io/badge/Platform-Docker%20%7C%20Windows%20%7C%20Linux-brightgreen" alt="Platform">
    <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python Version">
    <img src="https://img.shields.io/badge/Framework-FastAPI%20%7C%20Vue%203-orange" alt="Framework">
    <img src="https://img.shields.io/badge/License-MIT-lightgrey" alt="License">
  </p>
</div>

---

## 🌟 项目简介

**EchoSRT** 是一个音视频字幕自动化提取与翻译工具。提供WebUI，支持本地 GPU/CPU 推理以及云端 API 处理，提供一站式、全自动流水线解决方案。
## ✨ 核心特性

- **双引擎语音识别 (ASR)**：
  - **本地引擎**：内置 `faster-whisper`，自动探测 NVIDIA CUDA 硬件加速或回退 CPU 模式，支持 VAD 静音过滤、Beam Size 等高阶参数。
  - **云端引擎**：支持 OpenAI 格式的语音 API，针对超大文件实现了突破 25MB 限制的物理切片与时间戳重排机制。
- **大语言模型智能翻译 (LLM)**：基于并发信号量 (`asyncio.Semaphore`) 实现字幕分块异步翻译。支持 DeepSeek、ChatGPT 等任意兼容 OpenAI 接口的模型，结合上下文自动润色，生成“熟肉”字幕。
- **自动化非阻塞流水线**：后端基于 FastAPI + `asyncio.Queue` 实现多任务调度，支持批量下发处理。
- **可视化 Web 工作台**：Vue 3 驱动的极客终端风前端，提供实时 WebSocket 状态同步、滚动日志输出与看板式资产管理。
- **强大的分流代理机制**：支持按模块（模型下载 / 云端 ASR / LLM 翻译）独立接管 HTTP/SOCKS5 网络代理。
- **多平台 Docker 部署**：提供 CPU 和 GPU 独立镜像，支持快捷部署。

---

## 🚀 快速部署

### 方案一：Docker 部署 (推荐)

#### 1. 使用 Docker Compose 启动 (最简单)
已提供云端预编译镜像，在项目根目录下直接使用 `docker-compose` 启动：

```bash
# 启动 CPU 节点（适合绝大多数无显卡的家用 NAS 或服务器）
docker-compose up -d echosrt-cpu

# 或者：启动 GPU 节点（需在宿主机安装 NVIDIA Container Toolkit 及驱动）
docker-compose up -d echosrt-gpu
```

#### 2. 使用 Docker CLI 手动启动
使用 `docker run` 命令启动预编译镜像：
```bash
# CPU 版本
docker run -d --name echosrt-cpu \
  -p 8000:8000 \
  -v $(pwd)/workspace:/app/workspace \
  -v $(pwd)/models:/app/models \
  ghcr.io/siveci/echosrt:cpu-latest

# GPU 版本 (需增加 --gpus all 参数)
docker run -d --name echosrt-gpu \
  --gpus all \
  -p 8000:8000 \
  -v $(pwd)/workspace:/app/workspace \
  -v $(pwd)/models:/app/models \
  ghcr.io/siveci/echosrt:gpu-latest
```

#### 3. 手动构建镜像 (可选)
```bash
# 构建 CPU 镜像
docker build -t echosrt:cpu-local -f Dockerfile .

# 构建 GPU 镜像
docker build -t echosrt:gpu-local -f Dockerfile.gpu .

#构建完成后，将上述 `docker run` 命令中的镜像名称替换为构建的镜像名后运行
```

### 方案二：本地 Python 运行
```bash
# 1. 安装 FFmpeg
# Windows: 下载 FFmpeg 并在项目根目录创建 bin/ffmpeg/bin/ 放入 ffmpeg.exe
# Linux: sudo apt install ffmpeg

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 启动后台服务与 WebUI
python app.py
```

*(注：命令行交互，运行 `python main.py`)*

---

## 🛠️ 使用指南

### 1. 访问WebUI工作台
- 浏览器打开`http://127.0.0.1:8000`或`http://[远程IP]:8000`进入工作台
- 访问 `/docs` 查看 API 接口文档。。

### 2. 工作区与流水线
- 在 **[任务工作区]** 拖拽上传视频或音频文件，系统支持批量排队上传，音频文件将自动经过 FFmpeg 进行标准化 16kHz 单声道重采样。
- 勾选任务并点击“执行全量工作流”，后端会在后台自动串行执行提音、识别、翻译。

### 3. ASR 识别调优
- **本地模式**：对于含有大量环境噪音的视频，建议在「高级设置 -> 阈值过滤」中开启 **VAD 智能静音过滤**，减少模型的“幻觉”复读并提升推理速度。
- **云端模式**：长音频切片上传过程全自动完成，如果使用非官方的第三方代理接口，请注意调整大文件网络超时时间。

### 4. LLM 翻译设置
- 填入 API Base URL 和 API Key。
- 自定义 **Prompt** 强制大模型输出特定风格（例如语气、设定、特定角色人名映射等）。

---

## 📁 项目结构 (Monorepo)
```text
├── api/                # FastAPI 路由、服务逻辑与任务 Worker 车间
│   ├── routers/        # Web API 接口
│   ├── services/       # 配置层与文件流操作
│   └── workers/        # 异步队列消费进程
├── core/               # 底层算法库
├── frontend/           # 前端代码与静态资源
├── config/             # 配置文件目录
├── models/             # Faster-Whisper 离线模型文件
├── workspace/          # 音视频及字幕任务产物存储区
├── app.py              # WebUI & API 后端启动入口
├── main.py             # CLI 命令行交互入口
├── docker-compose.yml  
└── Dockerfile          
```

---

## ⚙️ 系统要求

| 维度 | 要求 |
| :--- | :--- |
| **操作系统** | Windows 10+ / Linux |
| **Docker** | 支持 linux/amd64 (GPU 版需具备 NVIDIA Runtime) |
| **Python** | 3.10 - 3.12（推荐 3.12.x） |
| **硬件(推荐)** | 至少 8GB 内存；使用本地 GPU 引擎推荐至少 6GB+ 显存的 NVIDIA 显卡 |

> **💡 Docker 权限说明**：如果在 NAS (如群晖、Unraid 等) 上部署遇到读写权限的问题，增加环境变量 `-e PUID=1000` 和 `-e PGID=1000` (替换为实际的 UID/GID)，容器将会自动对齐挂载目录的读写权限。

## TODO

- [x] **分流代理控制**：云端识别API和LLM 翻译API可独立选择是否使用全局代理，实现接入不同地区云端模型时分流代理。（v1.0.0 实装）
- [ ] **任务队列进度**：“全局队列面板”中直接显示具体的进度百分比/子状态。
- [ ] **LLM翻译断点续传**：LLM翻译模块增加“断点续传/缓存”机制。
- [ ] **空间管理优化**：提供“清理中间产物（如保留 SRT，删除 video 和 wav）”的配置选项，工作区面板显示每个任务及总任务占用的空间大小。
- [ ] **WebSocket断线重连**：加入 WebSocket 的断线自动重连机制（结合轮询 /api/task/status 作为兜底），以确保长任务的状态同步。
- [ ] **模型下载进度显示优化**：优化模型下载量的动态显示。
- [ ] **任务插队机制**：基于 `PriorityQueue`，允许紧急任务无视先来后到，插入正在执行的队列最前端。
- [ ] **智能静音切片**：解决超长音频一刀切断导致时间轴断裂与薛定谔“幻觉”的问题（支持静音区切片或 VAD 智能寻点）。
---

## ⚠️ 免责声明
1. **合法使用**：本项目仅供技术研究、个人视频剪辑与字幕制作辅助使用。
2. **接口规范**：请用户自行准备合规的 LLM API 及云端识别 API，确保使用不违反当地法律法规及服务商的使用条款。
3. **开源许可**：本项目基于 MIT 协议开源，完全免费，由第三方模型引起的任何输出内容问题概不负责。