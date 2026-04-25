import os
import shutil
import gc
from faster_whisper import WhisperModel

# 全局缓存模型实例，避免多次加载和释放时引发底层 CTranslate2/ONNX 的跨线程死锁
_cached_model = None
_cached_model_params = None

def unload_model():
    """显式卸载模型并释放显存"""
    global _cached_model, _cached_model_params
    if _cached_model is not None:
        del _cached_model
        _cached_model = None
        _cached_model_params = None
        # 强制进行 Python 垃圾回收，确保底层 C++ 对象被销毁，释放 VRAM
        gc.collect()
        print("[*] Whisper 模型已从显存中卸载。")

def transcribe_audio(
    audio_path: str,
    model_settings: dict,
    transcribe_settings: dict,
    vad_settings: dict
):
    global _cached_model, _cached_model_params

    model_size = model_settings.get("model_size", "large-v2")
    download_root = model_settings.get("download_root", "models")

    # 动态探测系统是否安装了 Nvidia 显卡驱动（跨平台兼容）
    if shutil.which("nvidia-smi"):
        device = "cuda"
        compute_type = "float16"  # 有 N 卡，直接火力全开（支持 Windows/Linux）
    else:
        device = "cpu"
        compute_type = "int8"     # 没有 N 卡（如 Mac 或纯 CPU 服务器），安全回退到 CPU 和 int8

    # 设定你自定义的模型存放路径 (例如当前项目下的 models 文件夹)
    custom_model_dir = os.path.join(os.getcwd(), download_root)
    
    current_params = (model_size, device, compute_type, custom_model_dir)
    
    # 命中缓存则复用，否则加载新模型
    if _cached_model is None or _cached_model_params != current_params:
        print(f"[*] 正在加载 Whisper 模型 ({model_size}) 到 {device.upper()} ({compute_type})...")
        _cached_model = WhisperModel(
            model_size, 
            device=device, 
            compute_type=compute_type,
            download_root=custom_model_dir
        )
        _cached_model_params = current_params
    
    print(f"[*] 开始识别音频: {audio_path}")
    
    # 将外层传入的参数传递给核心 transcribe 方法
    segments, info = _cached_model.transcribe(
        audio_path,
        **transcribe_settings,
        **vad_settings
    )
    
    print(f"[*] 识别到语言: {info.language} (概率: {info.language_probability:.2f})")
    return segments