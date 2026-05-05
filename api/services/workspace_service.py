import os
import json
import uuid
import asyncio
import shutil
from fastapi import UploadFile, HTTPException
from ..state import global_tasks_status
from core.audio_extractor import extract_audio
from .config_service import get_config
from ..ws_manager import manager

WORKSPACE_DIR = os.path.abspath(os.path.join(os.getcwd(), "workspace"))

async def save_asset(file: UploadFile, asset_type: str, task_id: str):
    if not task_id: task_id = str(uuid.uuid4())
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    meta_path, meta_data = os.path.join(task_dir, "meta.json"), {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f: meta_data = json.load(f)

    base_name = os.path.splitext(file.filename)[0]
    if "base_name" not in meta_data: meta_data["base_name"] = base_name

    # Bug 3 修复：上传新资产前，清理遗留的同类废弃文件，防止读取冲突
    if asset_type == "video": 
        for f in os.listdir(task_dir):
            if f.startswith("video."):
                try: os.remove(os.path.join(task_dir, f))
                except Exception: pass
        save_path = os.path.join(task_dir, f"video{os.path.splitext(file.filename)[1]}")
    elif asset_type == "audio": 
        if os.path.exists(os.path.join(task_dir, "audio.wav")):
            try: os.remove(os.path.join(task_dir, "audio.wav"))
            except Exception: pass
        save_path = os.path.join(task_dir, "audio.wav")
    elif asset_type == "srt": 
        if os.path.exists(os.path.join(task_dir, "original.srt")):
            try: os.remove(os.path.join(task_dir, "original.srt"))
            except Exception: pass
        save_path = os.path.join(task_dir, "original.srt")
    else: 
        raise HTTPException(status_code=400, detail="不支持的资产类型")
    
    def _save_file(src, dest):
        with open(dest, "wb") as buffer: shutil.copyfileobj(src, buffer, length=1024*1024*10)
            
    # Bug 4 修复：针对独立上传的音频，先保存为临时文件，再调用 FFmpeg 进行标准化重采样
    if asset_type == "audio":
        temp_audio_path = os.path.join(task_dir, f"temp_upload_{uuid.uuid4().hex[:8]}{os.path.splitext(file.filename)[1]}")
        await asyncio.to_thread(_save_file, file.file, temp_audio_path)
        try: await asyncio.to_thread(extract_audio, temp_audio_path, save_path)
        except Exception as e: raise HTTPException(status_code=500, detail=f"音频标准化重采样失败: {str(e)}")
        finally:
            if os.path.exists(temp_audio_path):
                try: os.remove(temp_audio_path)
                except Exception: pass
    else:
        await asyncio.to_thread(_save_file, file.file, save_path)
        
    with open(meta_path, "w", encoding="utf-8") as f: json.dump(meta_data, f, ensure_ascii=False)
        
    return {"task_id": task_id, "filename": file.filename, "message": f"{asset_type} 上传成功"}

async def get_download_file_path(task_id: str, type: str = "original"):
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    if not os.path.exists(task_dir): raise HTTPException(status_code=404, detail="任务目录不存在")
        
    meta_path, base_name = os.path.join(task_dir, "meta.json"), "output"
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f: base_name = json.load(f).get("base_name", "output")
            
    if type == "translated": 
        try:
            config_data = await get_config()
            lang_code = config_data.get("llm_settings", {}).get("target_language", "chs")
        except Exception:
            lang_code = "chs"
        target_file, out_name = os.path.join(task_dir, "translated.srt"), f"{base_name}_{lang_code}.srt"
    else: 
        target_file, out_name = os.path.join(task_dir, "original.srt"), f"{base_name}.srt"
    
    if not os.path.exists(target_file): raise HTTPException(status_code=404, detail="请求的字幕文件尚未生成或不存在")
    return target_file, out_name

def get_single_task(task_id: str):
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    if not os.path.exists(task_dir) or not os.path.isdir(task_dir):
        raise HTTPException(status_code=404, detail="任务不存在")
        
    meta_path, base_name = os.path.join(task_dir, "meta.json"), task_id[:8] + "..."
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f: base_name = json.load(f).get("base_name", base_name)
        except Exception: pass
            
    def check_valid(file_path):
        return os.path.exists(file_path) and os.path.getsize(file_path) > 5
        
    has_video = any(f.startswith("video.") and check_valid(os.path.join(task_dir, f)) for f in os.listdir(task_dir))
    
    return { "task_id": task_id, "base_name": base_name, "has_video": has_video, "has_audio": check_valid(os.path.join(task_dir, "audio.wav")), "has_original_srt": check_valid(os.path.join(task_dir, "original.srt")), "has_translated_srt": check_valid(os.path.join(task_dir, "translated.srt")), "created_at": os.path.getmtime(task_dir) }

def get_all_tasks():
    tasks = []
    if not os.path.exists(WORKSPACE_DIR): return tasks
        
    for task_id in os.listdir(WORKSPACE_DIR):
        task_dir = os.path.join(WORKSPACE_DIR, task_id)
        if not os.path.isdir(task_dir): continue
            
        meta_path, base_name = os.path.join(task_dir, "meta.json"), task_id[:8] + "..."
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f: base_name = json.load(f).get("base_name", base_name)
            except Exception: pass
                
        def check_valid(file_path):
            return os.path.exists(file_path) and os.path.getsize(file_path) > 5
            
        has_video = any(f.startswith("video.") and check_valid(os.path.join(task_dir, f)) for f in os.listdir(task_dir))
        
        tasks.append({ "task_id": task_id, "base_name": base_name, "has_video": has_video, "has_audio": check_valid(os.path.join(task_dir, "audio.wav")), "has_original_srt": check_valid(os.path.join(task_dir, "original.srt")), "has_translated_srt": check_valid(os.path.join(task_dir, "translated.srt")), "created_at": os.path.getmtime(task_dir) })
        
    return sorted(tasks, key=lambda x: x["created_at"], reverse=True)

def delete_task_workspace(task_id: str):
    if task_id in global_tasks_status:
        step = global_tasks_status[task_id].get("current_step")
        if step in ["pending_extract", "extracting", "pending_transcribe", "transcribing", "pending_translate", "translating"]:
            raise HTTPException(status_code=400, detail="该任务正在执行中，为防止文件损坏，无法删除！")
            
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    if os.path.exists(task_dir): 
        try:
            shutil.rmtree(task_dir)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"文件被占用或无法删除: {str(e)}")
    global_tasks_status.pop(task_id, None)
    manager.task_states.pop(task_id, None)
    return {"message": "任务删除成功"}