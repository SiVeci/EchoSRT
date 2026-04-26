# AutoSRT 🎬

基于 `faster-whisper` 的本地视频自动字幕提取工具

## 核心特性
- **极简操作**：浏览器拖拽上传视频，一键生成同名 `.srt` 字幕。
- **参数可视化**：支持高阶参数调优。
- **自动硬件加速**：自动探测系统是否包含 NVIDIA 显卡并启用 GPU 加速；无显卡或 Mac 环境下自动平滑回退至 CPU 运行。

## 环境准备
- Python >= 3.8
- FFmpeg 
  - *Windows*：可直接将 `ffmpeg.exe` 放入项目的 `ffmpeg/bin/` 目录下。
  - *Mac/Linux*：请通过包管理器全局安装（如 `brew install ffmpeg` 或 `sudo apt install ffmpeg`）。

- **NVIDIA GPU 加速环境 (可选但强烈推荐)**
  - 需要安装相应的 **NVIDIA 显卡驱动**。
  - 需配置 **CUDA Toolkit** (推荐 11.x 或 12.x) 及对应的 **cuDNN** 库，以便底层 `CTranslate2` 引擎能正常调用 GPU 算力。
  - *注：程序会自动探测系统环境。若未检测到 Nvidia 显卡或 CUDA 环境不完整，将平滑回退至纯 CPU 模式运行（Mac 设备也会自动使用 CPU），但处理速度会显著下降。*

## 使用方法

1. **安装运行依赖**
```bash
pip install faster-whisper fastapi "uvicorn[standard]" python-multipart websockets
```

2. **一键启动 WebUI**
   - **Windows 用户**：直接双击运行 `start.bat`
   - **Mac / Linux 用户**：在终端运行 `./start.sh` （首次运行前可能需要执行 `chmod +x start.sh`）

脚本会自动启动前后端服务，并在浏览器中为你打开 `http://127.0.0.1:8080` 的工作台。

> 💡 **保留的 CLI 命令行模式**：依然可以在终端直接运行 `python main.py` 在命令行提取字幕（首次运行会自动初始化配置文件）。

## TODO

- [ ] **HTTP 代理支持**：配置本地代理以加速 Hugging Face 大模型的下载。
- [ ] **在线模型聚合**：在模型选择界面直接获取并展示 Hugging Face 上的可用模型列表，支持本地缺失时自动下载。
- [ ] **Docker 容器化部署**：提供 Docker 镜像封装，方便在 NAS 或云服务器上一键运行部署。
