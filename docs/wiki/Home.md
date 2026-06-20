# EchoSRT — 字幕工作台 (v1.3.0)

**EchoSRT** 是一套高效的自动化视频翻译字幕流水线。它以 **FFmpeg + faster-whisper + LLM** 为核心引擎，提供从视频上传、媒体库扫描到字幕下载的一站式工作流方案。

---

## 核心功能

| 模块 | 能力 | 技术实现 |
|------|------|----------|
| <img src="icons/speaker.svg" width="16" height="16" style="vertical-align:-2px">&nbsp;**音频提取** | 从视频中提取 16kHz/mono WAV，支持音轨选择与时间段裁剪 | FFmpeg (`-map`, `-ss`, `-to`) |
| <img src="icons/mic.svg" width="16" height="16" style="vertical-align:-2px">&nbsp;**语音识别** | 本地 faster-whisper + 云端 OpenAI 兼容 API。支持 25MB+ 物理切片、说话人识别与词级时间戳 | `whisper_engine.py` / `api_transcribe.py` |
| <img src="icons/globe.svg" width="16" height="16" style="vertical-align:-2px">&nbsp;**字幕翻译** | LLM 异步并发 API 翻译 + 基于 GGUF 的本地离线翻译。支持 GPU 显存互斥调度 | `translate.py` / `local_llm_manager.py` |
| <img src="icons/link.svg" width="16" height="16" style="vertical-align:-2px">&nbsp;**实时监控** | WebSocket 全双工通信与状态同步，流式传输进度可视化 | `ws_manager.py` |
| <img src="icons/box.svg" width="16" height="16" style="vertical-align:-2px">&nbsp;**一键部署** | 基于 Docker Compose 的标准化部署，支持 CUDA/NVIDIA GPU 加速 | `docker-compose.yml` + `Dockerfile.gpu` |

---

## <img src="icons/layers.svg" width="20" height="20" style="vertical-align:-3px"> 技术栈一览

| 架构层 | 技术选型 |
| :--- | :--- |
| **前端** | Vue 3 + Element Plus |
| **后端** | FastAPI (Python 3.9 - 3.13) + asyncio |
| **引擎** | FFmpeg + faster-whisper + llama-cpp-python (GGUF) + OpenAI SDK |
| **通信** | REST API + WebSocket |
| **部署** | Docker / Docker Compose + NVIDIA Container Toolkit |

---

## <img src="icons/play.svg" width="20" height="20" style="vertical-align:-3px"> 适用场景

- **个人创作者**：为 YouTube/Bilibili 视频制作高质量双语字幕
- **字幕组**：批量处理剧集，自动化提取→识别→翻译全流程
- **研究者**：语音识别模型评测、翻译质量对比
- **NAS 用户**：通过 Docker 部署在群晖/Unraid/TrueNAS 上 7×24 运行

---

## <img src="icons/book.svg" width="20" height="20" style="vertical-align:-3px"> 文档导航

| 章节 | 说明 |
|------|------|
| [入门指南](安装指南) | 安装、快速上手、配置详解 |
| [用户指南](音频提取) | 工作区管理、音频提取、语音识别、翻译、下载 |
| [架构设计](架构总览) | 架构全景、流水线调度、WebSocket 通信、状态管理 |
| [API 参考](RESTAPI参考) | REST API 端点文档、WebSocket 消息格式 |
| [部署运维](Docker部署) | Docker 部署、GPU 配置、NAS 指南、代理方案 |
| [开发贡献](项目结构) | 项目结构、贡献指南、更新日志 |

---

## <img src="icons/zap.svg" width="20" height="20" style="vertical-align:-3px"> 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/SiVeci/EchoSRT.git
cd EchoSRT

# 2. Docker Compose 一键启动
docker compose up -d echosrt-cpu

# 3. 访问 Web UI
open http://localhost:8000
```

详细步骤请参阅 [快速上手](快速上手)。
