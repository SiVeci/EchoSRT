import os
import math
import json
import html
import re
import tempfile
from openai import OpenAI

try:
    from pydub import AudioSegment
    import platform
    import shutil
    
    # 动态指定 pydub 的 ffmpeg 路径，优先本地，其次系统全局
    system = platform.system()
    local_ffmpeg = os.path.join(os.getcwd(), "bin", "ffmpeg", "bin", "ffmpeg.exe" if system == "Windows" else "ffmpeg")
    if os.path.exists(local_ffmpeg):
        AudioSegment.converter = local_ffmpeg
    else:
        global_ffmpeg = shutil.which("ffmpeg")
        if global_ffmpeg:
            AudioSegment.converter = global_ffmpeg
except ImportError:
    AudioSegment = None

def format_time(seconds: float) -> str:
    """将秒数(浮点数)转换为 SRT 标准时间戳 (HH:MM:SS,mmm)"""
    hours = math.floor(seconds / 3600)
    seconds %= 3600
    minutes = math.floor(seconds / 60)
    seconds %= 60
    milliseconds = round((seconds - math.floor(seconds)) * 1000)
    seconds = math.floor(seconds)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

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

def run_api_transcription(
    audio_path: str,
    output_srt_path: str,
    asr_config: dict,
    progress_callback=None
):
    """
    调用云端标准 OpenAI Audio API 进行语音识别，直接生成 SRT 字幕。
    asr_config 结构示例:
    {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-...",
        "model_name": "whisper-1",
        "language": "zh",
        "prompt": ""
    }
    """
    api_key = (asr_config.get("api_key") or "").strip()
    base_url = (asr_config.get("base_url") or "https://api.openai.com/v1").strip()
    model_name = (asr_config.get("model_name") or "whisper-1").strip()
    language = (asr_config.get("language") or "").strip()
    prompt = (asr_config.get("prompt") or "").strip()
    
    # 新增高级增强参数
    translate_to_english = asr_config.get("translate", False)
    speaker_labels = asr_config.get("speaker_labels", False)
    word_timestamps = asr_config.get("word_timestamps", False)

    if not api_key:
        raise ValueError("缺少云端语音识别 API Key，请先在设置中配置。")

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"找不到需要识别的音频文件: {audio_path}")

    if not base_url:
        base_url = "https://api.openai.com/v1"

    use_verbose_json = speaker_labels or word_timestamps
    req_format = "verbose_json" if use_verbose_json else "srt"

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=300.0,  # 音频识别可能比较耗时，稍微给多一点超时时间
        max_retries=2
    )

    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    CHUNK_LIMIT_MB = 24.0

    if file_size_mb > CHUNK_LIMIT_MB:
        if AudioSegment is None:
            raise ImportError("音频文件超过 25MB，需要切片。请先在终端执行 'pip install pydub' 安装依赖库。")
        if progress_callback: 
            progress_callback(f"⚠️ 音频超过 25MB (当前 {file_size_mb:.1f}MB)，正在使用 pydub 智能切片...")
        else:
            print(f"[*] 音频超过 25MB，正在切片...")
        
        audio = AudioSegment.from_file(audio_path)
        chunk_length_ms = 10 * 60 * 1000  # 10 分钟为一个分片，16kHz Wav 大约占 18MB
        audio_chunks = [audio[i:i + chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]
    else:
        audio_chunks = [audio_path]
        chunk_length_ms = 0

    final_srt_content = ""
    current_srt_index = 1
    temp_dir = tempfile.gettempdir()

    try:
        for idx, chunk in enumerate(audio_chunks):
            is_file_path = isinstance(chunk, str)
            if not is_file_path:
                offset_seconds = (idx * chunk_length_ms) / 1000.0
                temp_chunk_path = os.path.join(temp_dir, f"echo_srt_temp_chunk_{idx}.wav")
                chunk.export(temp_chunk_path, format="wav")
                chunk_to_process = temp_chunk_path
                
                task_type = "翻译" if translate_to_english else "识别"
                if progress_callback: 
                    progress_callback(f"☁️ 正在处理并上传切片 {idx+1}/{len(audio_chunks)} ({task_type})...")
                else:
                    print(f"[*] 正在上传切片 {idx+1}/{len(audio_chunks)}...")
            else:
                offset_seconds = 0.0
                chunk_to_process = chunk
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
                        if translate_to_english: extra_body["timestamp_granularities"] = ["word"]
                        else: kwargs["timestamp_granularities"] = ["word"]
                            
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

                # 将本切片的时间轴集体加上 offset_seconds
                if len(audio_chunks) > 1:
                    shifted_srt, current_srt_index = parse_and_shift_srt(chunk_srt, offset_seconds, current_srt_index)
                    final_srt_content += shifted_srt + "\n\n"
                else:
                    final_srt_content += chunk_srt + "\n\n"

            finally:
                # 清理临时导出的分片文件
                if not is_file_path and os.path.exists(chunk_to_process):
                    try: os.remove(chunk_to_process)
                    except Exception: pass

        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(final_srt_content.strip() + "\n\n")
            
        if progress_callback: progress_callback("🎉 云端 API 处理完成！字幕已生成。")

    except Exception as e:
        raise Exception(f"云端语音处理接口请求失败: {e}")