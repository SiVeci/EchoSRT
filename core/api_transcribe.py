import os
import math
import json
import html
import re
import tempfile
import traceback
import httpx
import uuid
import wave

# [侦错探针 1] 导入 openai 库本身，以便捕获其特定的异常类型
import openai
from openai import OpenAI, APIStatusError, APIConnectionError

import platform
import shutil
import subprocess

def format_time(seconds: float) -> str:
    """将秒数(浮点数)转换为 SRT 标准时间戳 (HH:MM:SS,mmm)"""
    total_milliseconds = round(seconds * 1000)
    hours = total_milliseconds // 3600000
    remainder = total_milliseconds % 3600000
    minutes = remainder // 60000
    remainder %= 60000
    secs = remainder // 1000
    msecs = remainder % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{msecs:03d}"

def verbose_json_to_srt(response_data, use_words=False) -> str:
    """解析 verbose_json 格式数据，手动拼接成 SRT 字符串，支持说话人识别标签"""
    # 兼容 OpenAI SDK 各种返回实体 (Pydantic V2/V1 或原生 dict)
    if hasattr(response_data, "model_dump"):
        data = response_data.model_dump(exclude_none=True)
    elif hasattr(response_data, "dict"):
        data = response_data.dict(exclude_none=True)
    elif isinstance(response_data, dict):
        data = response_data
    else:
        try: data = json.loads(str(response_data))
        except Exception: return str(response_data)

    srt_lines = []
    items = data.get("words", []) if use_words and data.get("words") else data.get("segments", [])
        
    if not items:
        return data.get("text", "")

    for i, item in enumerate(items, start=1):
        start = item.get("start", 0.0)
        end = item.get("end", 0.0)
        text = item.get("word", item.get("text", "")).strip()
        
        # 提取非标的说话人标签 (Speaker Diarization)
        speaker = item.get("speaker")
        if speaker:
            text = f"[{speaker}]: {text}"

        srt_lines.append(f"{i}\n{format_time(start)} --> {format_time(end)}\n{text}\n")

    return "\n".join(srt_lines).strip()

def parse_and_shift_srt(srt_content: str, offset_seconds: float, start_index: int):
    """解析单段 SRT，将所有时间戳加上 offset_seconds，并重新进行序号递增编号"""
    blocks = srt_content.strip().split('\n\n')
    shifted_blocks = []
    current_idx = start_index
    time_pattern = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})")
    
    def add_offset(time_str):
        h, m, s_ms = time_str.split(':')
        s, ms = s_ms.split(',')
        total_seconds = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0 + offset_seconds
        return format_time(total_seconds)

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 2:
            time_line_idx = -1
            for i, line in enumerate(lines):
                if "-->" in line:
                    time_line_idx = i
                    break
            
            if time_line_idx != -1:
                time_match = time_pattern.search(lines[time_line_idx])
                if time_match:
                    start_time = add_offset(time_match.group(1))
                    end_time = add_offset(time_match.group(2))
                    text = "\n".join(lines[time_line_idx+1:])
                    shifted_blocks.append(f"{current_idx}\n{start_time} --> {end_time}\n{text}")
                    current_idx += 1
                    
    return "\n\n".join(shifted_blocks), current_idx

def get_audio_duration(file_path: str, fallback_duration: float) -> float:
    """获取音频的真实物理时长(秒)，防时间轴雪崩偏移"""
    try:
        with wave.open(file_path, 'rb') as wav_file:
            return wav_file.getnframes() / float(wav_file.getframerate())
    except Exception:
        pass
        
    system = platform.system()
    if system == "Windows":
        ffprobe_cmd = os.path.join(os.getcwd(), "bin", "ffmpeg", "bin", "ffprobe.exe")
    else:
        ffprobe_cmd = os.path.join(os.getcwd(), "bin", "ffmpeg", "bin", "ffprobe")
        
    ffprobe_cmd = ffprobe_cmd if os.path.exists(ffprobe_cmd) else shutil.which("ffprobe")
    if ffprobe_cmd:
        try:
            res = subprocess.run(
                [ffprobe_cmd, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )
            duration = float(res.stdout.strip())
            if duration > 0: return duration
        except Exception:
            pass
    return fallback_duration

def run_api_transcription(
    audio_path: str,
    output_srt_path: str,
    asr_config: dict,
    system_config: dict,
    progress_callback=None,
    cancel_event=None
):
    """
    调用云端标准 OpenAI Audio API 进行语音识别，直接生成 SRT 字幕。
    """
    api_key = (asr_config.get("api_key") or "").strip()
    base_url = (asr_config.get("base_url") or "https://api.openai.com/v1").strip()
    model_name = (asr_config.get("model_name") or "whisper-1").strip()
    language = (asr_config.get("language") or "").strip()
    prompt = (asr_config.get("prompt") or "").strip()
    
    translate_to_english = asr_config.get("translate", False)
    speaker_labels = asr_config.get("speaker_labels", False)
    word_timestamps = asr_config.get("word_timestamps", False)
    use_proxy = asr_config.get("use_network_proxy", False)
    enable_global_proxy = system_config.get("enable_global_proxy", False)
    proxy_url = system_config.get("network_proxy", "")

    actual_use_proxy = enable_global_proxy and use_proxy and proxy_url

    if not api_key:
        raise ValueError("缺少云端语音识别 API Key，请先在设置中配置。")

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"找不到需要识别的音频文件: {audio_path}")

    if not base_url:
        base_url = "https://api.openai.com/v1"

    use_verbose_json = speaker_labels or word_timestamps
    req_format = "verbose_json" if use_verbose_json else "srt"

    # 提取用户配置的超时时间，并做下限防呆保护
    timeout_cfg = asr_config.get("timeout_settings", {})
    try:
        user_connect = max(float(timeout_cfg.get("connect", 15.0)), 3.0)
        user_read = max(float(timeout_cfg.get("read", 300.0)), 30.0)
    except (TypeError, ValueError):
        user_connect, user_read = 15.0, 300.0
        
    # 组装精细化的 httpx Timeout 控制器
    timeout_config = httpx.Timeout(connect=user_connect, read=user_read, write=60.0, pool=10.0)

    client_params = {
        "api_key": api_key,
        "base_url": base_url,
        "max_retries": 2
    }
    if actual_use_proxy:
        client_params["http_client"] = httpx.Client(proxy=proxy_url, timeout=timeout_config)
    else:
        client_params["http_client"] = httpx.Client(proxy=None, trust_env=False, timeout=timeout_config)

    client = OpenAI(**client_params)

    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    CHUNK_LIMIT_MB = 24.0
    audio_chunks = []
    chunk_length_ms = 0

    if file_size_mb > CHUNK_LIMIT_MB:
        if progress_callback: 
            progress_callback(f"⚠️ 音频超过 25MB (当前 {file_size_mb:.1f}MB)，正在使用 FFmpeg 物理切片 (防 OOM)...")
        else:
            print(f"[*] 音频超过 25MB，正在进行防 OOM 物理切片...")
            
        chunk_length_sec = 5 * 60
        chunk_length_ms = chunk_length_sec * 1000
        task_uuid = uuid.uuid4().hex[:8]
        temp_dir = tempfile.gettempdir()
        segment_pattern = os.path.join(temp_dir, f"echo_srt_temp_chunk_{task_uuid}_%03d.wav")
        
        system = platform.system()
        if system == "Windows":
            local_ffmpeg = os.path.join(os.getcwd(), "bin", "ffmpeg", "bin", "ffmpeg.exe")
        else:
            local_ffmpeg = os.path.join(os.getcwd(), "bin", "ffmpeg", "bin", "ffmpeg")
            
        ffmpeg_cmd = local_ffmpeg if os.path.exists(local_ffmpeg) else shutil.which("ffmpeg")
        if not ffmpeg_cmd:
            raise FileNotFoundError("未找到 FFmpeg！请确保项目路径下存在 bin/ffmpeg 文件夹，或已在系统中安装 FFmpeg。")
            
        res = subprocess.run([
            ffmpeg_cmd, "-y", "-i", audio_path,
            "-f", "segment", "-segment_time", str(chunk_length_sec),
            "-ac", "1", "-ar", "16000",
            segment_pattern
        ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        
        if res.returncode != 0:
            raise RuntimeError(f"音频切片失败(防OOM机制错误)，FFmpeg 返回码: {res.returncode}, 错误: {res.stderr}")
        
        audio_chunks = []
        idx = 0
        while True:
            chunk_file = os.path.join(temp_dir, f"echo_srt_temp_chunk_{task_uuid}_{idx:03d}.wav")
            if os.path.exists(chunk_file):
                audio_chunks.append(chunk_file)
                idx += 1
            else:
                break
        
        if not audio_chunks:
            raise RuntimeError("音频切片失败：未生成任何片段，可能是原始音频文件损坏或不兼容。")
    else:
        audio_chunks = [audio_path]
        chunk_length_ms = 0

    final_srt_content = ""
    current_srt_index = 1
    temp_dir = tempfile.gettempdir()
    task_uuid = uuid.uuid4().hex[:8]

    current_offset = 0.0

    try:
        for idx, chunk in enumerate(audio_chunks):
            if cancel_event and cancel_event.is_set():
                if progress_callback:
                    progress_callback("⚠️ 检测到取消请求，终止云端识别...")
                raise Exception("任务已被手动中断")

            offset_seconds = current_offset
            chunk_to_process = chunk
            
            # 累加当前切片的真实物理时长作为下一个切片的起点 (防雪崩核心)
            if chunk_length_ms > 0:
                current_offset += get_audio_duration(chunk_to_process, fallback_duration=chunk_length_ms / 1000.0)

            if len(audio_chunks) > 1:
                task_type = "翻译" if translate_to_english else "识别"
                if progress_callback: 
                    progress_callback(f"☁️ 正在处理并上传切片 {idx+1}/{len(audio_chunks)} ({task_type})...")
                else:
                    print(f"[*] 正在上传切片 {idx+1}/{len(audio_chunks)}...")
            else:
                if progress_callback:
                    task_type = "翻译 (Translate to English)" if translate_to_english else "识别"
                    progress_callback(f"☁️ 正在上传音频并等待云端 API {task_type} (取决于音频长度和网络速度)...")
                else:
                    print("[*] 正在上传音频并等待云端 API 处理...")

            try:
                with open(chunk_to_process, "rb") as audio_file:
                    kwargs = { "model": model_name, "file": audio_file, "response_format": req_format }
                    if prompt: kwargs["prompt"] = prompt

                    extra_body = {}
                    if speaker_labels: extra_body["speaker_labels"] = True
                    if word_timestamps:
                        if not translate_to_english: kwargs["timestamp_granularities"] = ["word"]
                            
                    if extra_body: kwargs["extra_body"] = extra_body

                    if translate_to_english:
                        srt_response = client.audio.translations.create(**kwargs)
                    else:
                        if language and language.lower() not in ["auto", ""]:
                            kwargs["language"] = language
                        srt_response = client.audio.transcriptions.create(**kwargs)
            
                if req_format == "verbose_json":
                    chunk_srt = verbose_json_to_srt(srt_response, use_words=word_timestamps)
                else:
                    chunk_srt = str(srt_response) if not isinstance(srt_response, str) else srt_response
                    try:
                        parsed = json.loads(chunk_srt)
                        if isinstance(parsed, str): chunk_srt = parsed
                    except Exception: pass
                    chunk_srt = chunk_srt.replace("\\n", "\n")
                
                chunk_srt = html.unescape(chunk_srt)

                if len(audio_chunks) > 1:
                    shifted_srt, current_srt_index = parse_and_shift_srt(chunk_srt, offset_seconds, current_srt_index)
                    final_srt_content += shifted_srt + "\n\n"
                else:
                    final_srt_content += chunk_srt + "\n\n"

            finally:
                pass # 将清理移至最外层统筹处理

        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(final_srt_content.strip() + "\n\n")
            
        if progress_callback: progress_callback("🎉 云端 API 处理完成！字幕已生成。")

    except Exception as e:
        # [侦错探针 2] 详细捕获并打印不同类型的错误，而不是笼统地抛出一个新异常
        
        # 首先捕获 API 返回的 HTTP 状态错误 (如 401, 429, 500)
        if isinstance(e, APIStatusError):
            error_message = f"❌ 云端 API 返回状态错误 (HTTP Status: {e.status_code})！\n"
            error_message += f"   - 错误详情 (Response): {e.response.text}\n"
            print(error_message)
            raise Exception(error_message)
        
        # 其次捕获网络连接层面的错误 (如 DNS 解析失败, 连接超时)
        elif isinstance(e, APIConnectionError):
            error_message = f"❌ 无法连接到云端 API 服务器！请检查网络或代理设置。\n   - 错误根源: {e.__cause__}\n"
            print(error_message)
            raise Exception(error_message)
            
        # 最后捕获所有其他未知错误，并打印完整的堆栈信息
        else:
            print(f"❌ 云端语音处理流程发生未知错误: {e}")
            traceback.print_exc() # 打印完整的错误调用堆栈，这是最重要的排查线索
            raise
            
    finally:
        # [内存/句柄泄漏修复] 强制关闭自定义传入的 HTTP 客户端，释放底层 Socket 资源
        try:
            client_params["http_client"].close()
        except Exception:
            pass
            
        # 兜底清理切片残留，防大音频中断塞爆临时目录
        if chunk_length_ms > 0:
            for chunk in audio_chunks:
                if os.path.exists(chunk):
                    try: os.remove(chunk)
                    except Exception: pass
