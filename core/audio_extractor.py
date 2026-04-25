import subprocess
import os
import platform
import shutil

def extract_audio(video_path: str, output_audio_path: str) -> str:
    """使用 FFmpeg 从视频中提取 16kHz 单声道音频"""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")
    
    # 跨平台判断：优先使用本地 FFmpeg，如果没有则使用系统全局 FFmpeg
    system = platform.system()
    if system == "Windows":
        local_ffmpeg = os.path.join(os.getcwd(), "bin", "ffmpeg", "bin", "ffmpeg.exe")
    else:
        local_ffmpeg = os.path.join(os.getcwd(), "bin", "ffmpeg", "bin", "ffmpeg")
        
    if os.path.exists(local_ffmpeg):
        ffmpeg_cmd = local_ffmpeg
    else:
        ffmpeg_cmd = shutil.which("ffmpeg")
        if not ffmpeg_cmd:
            raise FileNotFoundError("未找到 FFmpeg！请确保项目路径下存在 bin/ffmpeg 文件夹，或已在系统中安装 FFmpeg。")

    command = [
        ffmpeg_cmd,
        "-y",                  
        "-i", video_path,      
        "-vn",                 
        "-acodec", "pcm_s16le",
        "-ar", "16000",        
        "-ac", "1",            
        output_audio_path
    ]
    
    print(f"[*] 正在提取音频至临时文件: {output_audio_path}")
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 提取音频失败:\n{result.stderr}")
    
    return output_audio_path