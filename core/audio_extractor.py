import subprocess
import os
import platform
import shutil
import re
import queue
import threading
import time

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

    # 增加 CREATE_NO_WINDOW 避免 Windows 下多个 FFmpeg 并发抢占控制台引发报错
    creation_flags = 0
    if system == "Windows":
        creation_flags = subprocess.CREATE_NO_WINDOW
        
    command = [
        ffmpeg_cmd,
        "-y",
        "-err_detect", "ignore_err",
        "-ignore_unknown",
        "-fflags", "+discardcorrupt",
        "-i", video_path
    ]

    if ffmpeg_settings:
        if ffmpeg_settings.get("audio_track"):
            command.extend(["-map", str(ffmpeg_settings["audio_track"])])
        if ffmpeg_settings.get("start_time"):
            command.extend(["-ss", str(ffmpeg_settings["start_time"])])
        if ffmpeg_settings.get("end_time"):
            command.extend(["-to", str(ffmpeg_settings["end_time"])])
            
    command.extend([
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_audio_path
    ])
        
    print(f"[*] 正在提取音频至临时文件: {output_audio_path}")
    
    # 使用 Popen 进行流式读取
    # 增加 stdin=subprocess.DEVNULL 防止 Windows 后台线程报错 -22 (4294967274)
    # 增加 errors='ignore' 防止控制台输出乱码导致 Python 崩溃
    process = subprocess.Popen(
        command, 
        stdout=subprocess.DEVNULL, 
        stderr=subprocess.PIPE, 
        stdin=subprocess.DEVNULL,
        text=True, 
        errors='ignore',
        creationflags=creation_flags
    )
    
    # 预编译正则，用于匹配 FFmpeg 日志中的 time=HH:MM:SS.xx
    time_pattern = re.compile(r"time=(\d{2}:\d{2}:\d{2})\.\d+")
    error_log = []
    muxing_completed = False
    
    out_queue = queue.Queue()
    
    def enqueue_output(out, q):
        try:
            for line in iter(out.readline, ''):
                if line: q.put(line)
        except Exception:
            pass
        finally:
            q.put(None)
            try: out.close()
            except Exception: pass
            
    t = threading.Thread(target=enqueue_output, args=(process.stderr, out_queue))
    t.daemon = True
    t.start()
    
    last_output_time = time.time()
    
    try:
        while True:
            try:
                line = out_queue.get(timeout=1.0)
                if line is None:
                    break
                    
                last_output_time = time.time()
                line_str = line.strip()
                if line_str:
                    error_log.append(line_str)
                    if len(error_log) > 5:
                        error_log.pop(0)
                        
                    if "muxing overhead:" in line_str:
                        muxing_completed = True
                        
                match = time_pattern.search(line)
                if match and progress_callback:
                    progress_callback(match.group(1))
                    
            except queue.Empty:
                if process.poll() is not None:
                    break
                if time.time() - last_output_time > 60:
                    raise TimeoutError("FFmpeg 进程长达 60 秒无任何输出，判定为死锁挂起，已自动中断。")
                    
        process.wait()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    
    if process.returncode != 0:
        # 如果 FFmpeg 输出了完整的 muxing summary，说明即使遇到损坏帧，文件也已经完整生成，应当放行
        if muxing_completed and os.path.exists(output_audio_path):
            print(f"[⚠️ 警告] FFmpeg 提取遇到损坏的音频帧 (代码 {process.returncode})，但已成功完成提取，自动放行...")
        else:
            err_msg = " | ".join(error_log) if error_log else "未知原因"
            raise RuntimeError(f"FFmpeg 提取失败 (代码 {process.returncode})，详情: {err_msg}")
    
    return output_audio_path