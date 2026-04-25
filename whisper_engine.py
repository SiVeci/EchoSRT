import os
import shutil
from faster_whisper import WhisperModel

def transcribe_audio(
    audio_path: str,
    model_settings: dict,
    transcribe_settings: dict,
    vad_settings: dict
):
    model_size = model_settings.get("model_size", "large-v2")
    download_root = model_settings.get("download_root", "models")

    # 动态探测系统是否安装了 Nvidia 显卡驱动（跨平台兼容）
    if shutil.which("nvidia-smi"):
        device = "cuda"
        compute_type = "float16"  # 有 N 卡，直接火力全开（支持 Windows/Linux）
    else:
        device = "cpu"
        compute_type = "int8"     # 没有 N 卡（如 Mac 或纯 CPU 服务器），安全回退到 CPU 和 int8

    print(f"[*] 正在加载 Whisper 模型 ({model_size}) 到 {device.upper()} ({compute_type})...")
    
    # 设定你自定义的模型存放路径 (例如当前项目下的 models 文件夹)
    custom_model_dir = os.path.join(os.getcwd(), download_root)
    
    # 加入 download_root 参数
    model = WhisperModel(
        model_size, 
        device=device, 
        compute_type=compute_type,
        download_root=custom_model_dir  # <--- 新增这行
    )
    
    print(f"[*] 开始识别音频: {audio_path}")
    
    # 将外层传入的参数传递给核心 transcribe 方法
    segments, info = model.transcribe(
        audio_path,
        **transcribe_settings,
        **vad_settings
    )
    
    print(f"[*] 识别到语言: {info.language} (概率: {info.language_probability:.2f})")
    return segments