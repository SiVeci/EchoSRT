import os
import shutil
import gc

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from faster_whisper import WhisperModel

_cached_model = None
_cached_model_params = None

def unload_model():
    global _cached_model, _cached_model_params
    if _cached_model is not None:
        del _cached_model
        _cached_model = None
        _cached_model_params = None
        gc.collect()
        print("[*] Whisper 模型已从显存中卸载。")

def transcribe_audio(
    audio_path: str,
    model_settings: dict,
    transcribe_settings: dict,
    vad_settings: dict,
    system_config: dict
):
    global _cached_model, _cached_model_params

    model_size = model_settings.get("model_size", "large-v2")
    download_root = model_settings.get("download_root", "models")
    use_proxy = system_config.get("use_proxy_for_model_download", False)
    proxy_url = system_config.get("network_proxy", "")

    if use_proxy and proxy_url:
        os.environ['HTTP_PROXY'] = proxy_url
        os.environ['HTTPS_PROXY'] = proxy_url

    if shutil.which("nvidia-smi"):
        device = "cuda"
        compute_type = "float16"
    else:
        device = "cpu"
        compute_type = "int8"

    custom_model_dir = os.path.join(os.getcwd(), download_root)
    
    current_params = (model_size, device, compute_type, custom_model_dir)
    
    if _cached_model is None or _cached_model_params != current_params:
        print(f"[*] 正在加载 Whisper 模型 ({model_size}) 到 {device.upper()} ({compute_type})...")
        _cached_model = WhisperModel(
            model_size, 
            device=device, 
            compute_type=compute_type,
            download_root=custom_model_dir
        )
        _cached_model_params = current_params
    
    if use_proxy and proxy_url:
        if 'HTTP_PROXY' in os.environ:
            del os.environ['HTTP_PROXY']
        if 'HTTPS_PROXY' in os.environ:
            del os.environ['HTTPS_PROXY']

    print(f"[*] 开始识别音频: {audio_path}")
    
    transcribe_kwargs = transcribe_settings.copy()
    transcribe_kwargs.pop("engine", None)
    
    segments, info = _cached_model.transcribe(
        audio_path,
        **transcribe_kwargs,
        **vad_settings
    )
    
    print(f"[*] 识别到语言: {info.language} (概率: {info.language_probability:.2f})")
    return segments