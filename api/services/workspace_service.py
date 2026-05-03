import os
import json
import uuid
import asyncio
import shutil
from fastapi import UploadFile, HTTPException
from ..state import global_tasks_status

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

    if asset_type == "video": save_path = os.path.join(task_dir, f"video{os.path.splitext(file.filename)[1]}")
    elif asset_type == "audio": save_path = os.path.join(task_dir, "audio.wav")
    elif asset_type == "srt": save_path = os.path.join(task_dir, "original.srt")
    else: raise HTTPException(status_code=400, detail="不支持的资产类型")
    
    def _save_file(src, dest):
        with open(dest, "wb") as buffer: shutil.copyfileobj(src, buffer, length=1024*1024*10)
            
    await asyncio.to_thread(_save_file, file.file, save_path)
    with open(meta_path, "w", encoding="utf-8") as f: json.dump(meta_data, f, ensure_ascii=False)
        
    return {"task_id": task_id, "filename": file.filename, "message": f"{asset_type} 上传成功"}

def get_download_file_path(task_id: str, type: str = "original"):
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    if not os.path.exists(task_dir): raise HTTPException(status_code=404, detail="任务目录不存在")
        
    meta_path, base_name = os.path.join(task_dir, "meta.json"), "output"
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f: base_name = json.load(f).get("base_name", "output")
            
    if type == "translated": target_file, out_name = os.path.join(task_dir, "translated.srt"), f"{base_name}_chs.srt"
    else: target_file, out_name = os.path.join(task_dir, "original.srt"), f"{base_name}.srt"
    
    if not os.path.exists(target_file): raise HTTPException(status_code=404, detail="请求的字幕文件尚未生成或不存在")
    return target_file, out_name

async def get_all_tasks():
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
                
        tasks.append({ "task_id": task_id, "base_name": base_name, "has_video": any(f.startswith("video.") for f in os.listdir(task_dir)), "has_audio": os.path.exists(os.path.join(task_dir, "audio.wav")), "has_original_srt": os.path.exists(os.path.join(task_dir, "original.srt")), "has_translated_srt": os.path.exists(os.path.join(task_dir, "translated.srt")), "created_at": os.path.getmtime(task_dir) })
        
    return sorted(tasks, key=lambda x: x["created_at"], reverse=True)

def delete_task_workspace(task_id: str):
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    if os.path.exists(task_dir): shutil.rmtree(task_dir)
    global_tasks_status.pop(task_id, None)
    return {"message": "任务删除成功"}