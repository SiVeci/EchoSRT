import subprocess
import os
import platform
import shutil
import re

def extract_audio(video_path: str, output_audio_path: str, progress_callback=None, ffmpeg_settings: dict = None) -> str:
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
        "-i", video_path
    ]

    if ffmpeg_settings:
        if ffmpeg_settings.get("start_time"):
            command.extend(["-ss", str(ffmpeg_settings["start_time"])])
        if ffmpeg_settings.get("end_time"):
            command.extend(["-to", str(ffmpeg_settings["end_time"])])
        if ffmpeg_settings.get("audio_track"):
            command.extend(["-map", str(ffmpeg_settings["audio_track"])])

    command.extend([
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_audio_path
    ])
    
    print(f"[*] 正在提取音频至临时文件: {output_audio_path}")
    
    # 使用 Popen 进行流式读取
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, universal_newlines=True)
    
    # 预编译正则，用于匹配 FFmpeg 日志中的 time=HH:MM:SS.xx
    time_pattern = re.compile(r"time=(\d{2}:\d{2}:\d{2})\.\d+")
    
    # 逐行读取 stderr (FFmpeg 的日志默认输出在 stderr)
    for line in process.stderr:
        match = time_pattern.search(line)
        if match and progress_callback:
            # 提取出 HH:MM:SS 并回调
            progress_callback(match.group(1))
            
    process.wait()
    
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg 提取音频失败，返回码 {process.returncode}")
    
    return output_audio_path