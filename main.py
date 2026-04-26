import os
import json
import platform
import shutil
from core.audio_extractor import extract_audio
from core.whisper_engine import transcribe_audio
from core.srt_formatter import generate_srt

def main():
    print("=== 本地 GPU 视频自动提取字幕工具 ===")
    
    # 如果不存在 config.json，则自动从 example 复制一份
    if not os.path.exists("config.json"):
        if os.path.exists("config.example.json"):
            shutil.copy("config.example.json", "config.json")
            print("[*] 首次运行，已自动生成 config.json 默认配置文件。")

    # 尝试加载配置文件
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"[错误] 读取 config.json 失败: {e}")
        return
        
    # 从配置中读取并设置 HF_TOKEN
    hf_token = config.get("secrets", {}).get("hf_token", "")
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token

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

    try:
        # 步骤 1: 提取音频
        extract_audio(video_path, temp_audio_path)
        
        # 步骤 2: 语音识别
        segments = transcribe_audio(
            temp_audio_path,
            model_settings=config.get("model_settings", {}),
            transcribe_settings=config.get("transcribe_settings", {}),
            vad_settings=config.get("vad_settings", {})
        )
        
        # 步骤 3: 格式化为 SRT 字幕
        generate_srt(segments, output_srt_path)
        
    except Exception as e:
        print(f"\n[程序异常中止] 错误详情: {e}")
        
    finally:
        # 步骤 4: 清理临时文件
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            print(f"[*] 已清理临时音频文件: {temp_audio_path}")

if __name__ == "__main__":
    main()