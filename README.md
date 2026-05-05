# EchoSRT v1.0.0

EchoSRT 是一个基于 `faster-whisper` 和 LLM API 的音视频字幕提取与翻译工具。

## 技术特性
- **异步流水线**: 后端采用 FastAPI 配合 `asyncio.Queue` 实现提取、识别与翻译阶段的非阻塞任务调度。
- **Web 前端**: 基于 Vue 3 构建，通过 WebSocket 提供双向状态同步与日志输出。
- **ASR 识别引擎**:
  - **本地模型**: 封装 `faster-whisper` (CTranslate2 引擎)。自动探测系统环境，支持 CUDA (float16) 与 CPU (int8) 推理。对外暴露 VAD 过滤、Beam Size、Temperature 等解码层参数。
  - **API 接入**: 兼容 OpenAI Audio API。针对超过 25MB 的文件限制，在本地实现固定时长的物理切片与时间戳重排机制。
- **LLM 翻译模块**: 基于 `AsyncOpenAI` 与并发信号量 (`asyncio.Semaphore`) 实现字幕分块异步翻译。支持对携带 `<think>` 等非标准输出标签的模型进行正则清洗。
- **代理与分流**: 支持全局或模块级别 (模型下载 / 在线 ASR / LLM) 独立配置 HTTP/SOCKS5 代理。

## 环境准备

- Python >= 3.8
- FFmpeg 
  - Windows: 将执行文件放置于 `bin/ffmpeg/bin/` 目录下。
  - Mac/Linux: 需安装至系统环境变量 `PATH` 中。
- (可选) NVIDIA GPU 环境: 需配置对应的 NVIDIA 驱动、CUDA Toolkit 及 cuDNN 以激活显卡计算。

## 使用方法

### Docker 部署

镜像已发布至 GHCR。在项目根目录下执行以下命令启动容器：

```bash
# 启动 CPU 节点
docker-compose up -d echosrt-cpu

# 启动 GPU 节点 (需在宿主机安装 NVIDIA Container Toolkit)
docker-compose up -d echosrt-gpu
```
启动后，浏览器访问 `http://[IP]:8000` 即可进入工作台。

如果你想修改源码进行二次开发或定制 Docker 环境，请打开 docker-compose.yml，注释掉 image: 配置行并取消 build: 块的注释。然后执行 docker-compose up -d --build 进行构建。服务启动后通过http://[宿主机IP]:8000访问

### 源码运行

1. **安装运行依赖**
建议通过项目根目录下的 `requirements.txt` 一键安装所有必备依赖（包含视频提取、语音识别以及 LLM 翻译所需的核心库）：
```bash
pip install -r requirements.txt
```

2. **启动服务**
```bash
python app.py
```

脚本会自动启动后端 API 及静态页面托管，浏览器访问 `http://127.0.0.1:8000` 即可进入工作台；访问 `http://127.0.0.1:8000/docs` 可查看二次开发 API 接口文档。

> 💡 **保留的 CLI 命令行模式**：依然可以在终端直接运行 `python main.py` 在命令行提取字幕（首次运行会自动初始化配置文件）。

## TODO

- [x] **分流代理控制**：云端识别API和LLM 翻译API可独立选择是否使用全局代理，实现接入不同地区云端模型时分流代理。（v1.0.0 实装）
- [ ] **任务队列进度**：“全局队列面板”中直接显示具体的进度百分比/子状态。
- [ ] **LLM翻译断点续传**：LLM翻译模块增加“断点续传/缓存”机制。
- [ ] **空间管理优化**：提供“清理中间产物（如保留 SRT，删除 video 和 wav）”的配置选项，工作区面板显示每个任务及总任务占用的空间大小。
- [ ] **WebSocket断线重连**：加入 WebSocket 的断线自动重连机制（结合轮询 /api/task/status 作为兜底），以确保长任务的状态同步。
- [ ] **模型下载进度显示优化**：优化模型下载量的动态显示。
