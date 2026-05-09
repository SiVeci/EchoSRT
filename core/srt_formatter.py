import math

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

def generate_srt(segments, output_srt_path: str, progress_callback=None):
    """将识别片段格式化并写入 .srt 文件"""
    print(f"[*] 正在生成字幕文件: {output_srt_path}")
    
    with open(output_srt_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(segments, start=1):
            start_time = format_time(segment.start)
            end_time = format_time(segment.end)
            text = segment.text.strip()
            
            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{text}\n\n")
            
            if progress_callback:
                progress_callback(start_time, end_time, text)
            
    print(f"[*] 字幕生成完毕！")