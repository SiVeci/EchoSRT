# AutoSRT 🎬

本地视频自动提取字幕工具。

## 系统要求

- **操作系统**：Windows / Linux / macOS
- **环境依赖**：Python >= 3.8
- **硬件配置**：推荐使用配备 NVIDIA 显卡的电脑（程序会自动启用 GPU 加速）。若无独立显卡或在 Mac 环境下，程序会自动回退至纯 CPU 模式运行。
- **外部组件**：程序依赖 `FFmpeg` 提取音频。
  - *Windows 用户*：可直接将下载好的 `ffmpeg.exe` 放置在项目的 `ffmpeg/bin/` 目录下。
  - *Linux / macOS 用户*：请通过包管理器全局安装（如 `sudo apt install ffmpeg` 或 `brew install ffmpeg`）。

## 使用方法

1. **安装依赖**
   ```bash
   pip install faster-whisper
   ```

2. **准备配置文件**
   修改 `config.example.json` ，并重命名为 `config.json`。

3. **运行程序**
   ```bash
   python main.py
   ```

4. **生成字幕**
   根据控制台提示，将视频文件直接拖拽到窗口中并按回车，即可在视频同目录下自动生成同名的 `.srt` 字幕文件。

> 💡 **提示**：如需修改模型大小、语言或提示词等进阶参数，请直接编辑 `config.json` 文件。
