import os
import json
import platform
import shutil
import asyncio
from core.audio_extractor import extract_audio
from core.whisper_engine import transcribe_audio
from core.srt_formatter import generate_srt
from core.translate import run_llm_translation
from core.api_transcribe import run_api_transcription

def set_global_proxy(system_settings: dict):
    """动态配置系统代理与防呆纠正"""
    proxy_url = system_settings.get("network_proxy", "").strip()
    enable_global = system_settings.get("enable_global_proxy", False)
    
    if enable_global and proxy_url:
        proxy = proxy_url
        if proxy.startswith("socks5://"): proxy = proxy.replace("socks5://", "socks5h://", 1)
        elif not proxy.startswith("http://") and not proxy.startswith("https://") and not proxy.startswith("socks5h://"):
            proxy = f"http://{proxy}"
        
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy
        os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
        print(f"[*] 已启用全局网络代理: {proxy}")
    else:
        for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY"]:
            os.environ.pop(k, None)

def resolve_active_profile(settings: dict) -> dict:
    """从设置中解析出当前激活的 Profile 并将其字段平铺到根部"""
    if not settings or "profiles" not in settings:
        return settings
    active_id = settings.get("active_profile_id", "default")
    profiles = settings.get("profiles", [])
    if not profiles:
        return settings
    profile = next((p for p in profiles if p["id"] == active_id), profiles[0])
    new_settings = settings.copy()
    new_settings.update(profile)
    return new_settings

def main():
    print("=== 本地 GPU 视频自动提取字幕工具 ===")
    
    # 如果不存在 config.json，则自动从 example 复制一份 (已迁移至 config 目录)
    if not os.path.exists("config/config.json"):
        if os.path.exists("config/config.example.json"):
            os.makedirs("config", exist_ok=True)
            shutil.copy("config/config.example.json", "config/config.json")
            print("[*] 首次运行，已自动生成 config/config.json 默认配置文件。")

    # 尝试加载配置文件
    try:
        with open("config/config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"[错误] 读取 config/config.json 失败: {e}")
        return
        
    # 从配置中读取并设置 HF_TOKEN
    hf_token = config.get("secrets", {}).get("hf_token", "")
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token

    # 设置全局代理
    set_global_proxy(config.get("system_settings", {}))

    # 提示用户输入视频路径，并去除两端可能存在的文件路径引号（处理文件拖拽的情况）
    video_path = input("请输入需要处理的视频文件路径: ").strip('\"\'')
    
    # 处理 Linux/macOS 终端拖拽时可能产生的反斜杠转义空格
    if platform.system() != "Windows":
        video_path = video_path.replace('\\ ', ' ')
    
    # 将相对路径（如直接输入的文件名）转换为绝对路径，确保程序后续处理和保存路径正确
    video_path = os.path.abspath(video_path)
    
    # 校验输入文件
    if not os.path.exists(video_path):
        print(f"[错误] 找不到输入文件: {video_path}")
        return

    # 动态构建输出路径 (与原视频同目录)
    base_name = os.path.splitext(video_path)[0]
    temp_audio_path = f"{base_name}_temp.wav"
    output_srt_path = f"{base_name}.srt"
    output_translated_path = f"{base_name}_translated.srt"

    try:
        # 步骤 1: 提取音频
        extract_audio(
            video_path, 
            temp_audio_path, 
            ffmpeg_settings=config.get("ffmpeg_settings", {})
        )
        
        # 步骤 2 & 3: 语音识别与字幕生成
        transcribe_settings = config.get("transcribe_settings", {})
        engine = transcribe_settings.get("engine", "local")
        
        if engine == "api":
            print("\n[*] 正在调用云端 API 进行语音识别...")
            asr_config = resolve_active_profile(config.get("online_asr_settings", {}))
            run_api_transcription(
                audio_path=temp_audio_path,
                output_srt_path=output_srt_path,
                asr_config=asr_config,
                system_config=config.get("system_settings", {})
            )
        else:
            print("\n[*] 正在使用本地 Whisper 模型进行语音识别...")
            segments = transcribe_audio(
                temp_audio_path,
                model_settings=config.get("model_settings", {}),
                transcribe_settings=transcribe_settings,
                vad_settings=config.get("vad_settings", {}),
                system_config=config.get("system_settings", {})
            )
            generate_srt(segments, output_srt_path)
        
        # 步骤 4: LLM 智能翻译 (可选)
        llm_settings = resolve_active_profile(config.get("llm_settings", {}))
        if llm_settings.get("api_key"):
            choice = input(f"\n[*] 检测到已配置大模型 API Key，是否继续进行智能翻译出熟肉？(y/N): ").strip().lower()
            if choice == 'y':
                print(f"[*] 正在调用大模型进行翻译，目标语言: {llm_settings.get('target_language', 'zh')}")
                asyncio.run(run_llm_translation(
                    input_srt_path=output_srt_path,
                    output_srt_path=output_translated_path,
                    llm_config=llm_settings,
                    system_config=config.get("system_settings", {})
                ))
        
    except Exception as e:
        print(f"\n[程序异常中止] 错误详情: {e}")
        
    finally:
        # 步骤 5: 清理临时文件
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            print(f"[*] 已清理临时音频文件: {temp_audio_path}")

if __name__ == "__main__":
    main()