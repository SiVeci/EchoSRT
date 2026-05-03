import os
import json
import uuid
import asyncio
import shutil
import socket
import urllib.parse
from fastapi import APIRouter, UploadFile, File, Form, Body, HTTPException
from fastapi.responses import FileResponse

from ..state import q_extract, q_transcribe, q_translate, global_tasks_status

router = APIRouter()
WORKSPACE_DIR = os.path.abspath(os.path.join(os.getcwd(), "workspace"))

@router.post("/upload/{asset_type}")
async def upload_asset(asset_type: str, file: UploadFile = File(...), task_id: str = Form(None)):
    if not task_id:
        task_id = str(uuid.uuid4())
    
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    meta_path = os.path.join(task_dir, "meta.json")
    meta_data = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta_data = json.load(f)

    base_name = os.path.splitext(file.filename)[0]
    if "base_name" not in meta_data:
        meta_data["base_name"] = base_name

    if asset_type == "video":
        ext = os.path.splitext(file.filename)[1]
        save_path = os.path.join(task_dir, f"video{ext}")
    elif asset_type == "audio":
        save_path = os.path.join(task_dir, "audio.wav")
    elif asset_type == "srt":
        save_path = os.path.join(task_dir, "original.srt")
    else:
        raise HTTPException(status_code=400, detail="不支持的资产类型")
    
    def _save_file(src, dest):
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(src, buffer, length=1024*1024*10)
            
    await asyncio.to_thread(_save_file, file.file, save_path)
        
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, ensure_ascii=False)
        
    return {"task_id": task_id, "filename": file.filename, "message": f"{asset_type} 上传成功"}

@router.post("/task/execute")
async def execute_task(payload: dict = Body(...)):
    task_id = payload.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="缺少 task_id")
        
    steps = payload.get("steps", [])
    if not steps:
        raise HTTPException(status_code=400, detail="未指定执行步骤")

    proxy_url = payload.get("system_settings", {}).get("network_proxy", "").strip()
    if proxy_url:
        try:
            test_url = proxy_url if "://" in proxy_url else f"http://{proxy_url}"
            parsed = urllib.parse.urlparse(test_url)
            host, port = parsed.hostname, parsed.port
            if not host or not port: raise ValueError("地址或端口为空")
            with socket.create_connection((host, port), timeout=3.0): pass
        except Exception as e:
            err_msg = f"连接配置的代理服务器 ({host}:{port}) 失败，请检查或关闭代理开关。({str(e)})"
            raise HTTPException(status_code=400, detail=err_msg)

    config_to_save = {k: v for k, v in payload.items() if k not in ["task_id", "steps"]}
    try:
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config_to_save, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[警告] 无法保存最新配置到 config.json: {e}")

    global_tasks_status[task_id] = {
        "steps": steps,
        "current_step": "pending",
        "config": payload
    }

    if "extract" in steps:
        global_tasks_status[task_id]["current_step"] = "pending_extract"
        await q_extract.put((task_id, payload))
    elif "transcribe" in steps:
        global_tasks_status[task_id]["current_step"] = "pending_transcribe"
        await q_transcribe.put((task_id, payload))
    elif "translate" in steps:
        global_tasks_status[task_id]["current_step"] = "pending_translate"
        await q_translate.put((task_id, payload))

    return {"task_id": task_id, "message": "工作流已加入流水线队列"}

@router.get("/download/{task_id}")
async def download_srt(task_id: str, type: str = "original"):
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    if not os.path.exists(task_dir):
        raise HTTPException(status_code=404, detail="任务目录不存在")
        
    meta_path = os.path.join(task_dir, "meta.json")
    base_name = "output"
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            base_name = json.load(f).get("base_name", "output")
            
    if type == "translated":
        target_file, out_name = os.path.join(task_dir, "translated.srt"), f"{base_name}_chs.srt"
    else:
        target_file, out_name = os.path.join(task_dir, "original.srt"), f"{base_name}.srt"
    
    if not os.path.exists(target_file):
        raise HTTPException(status_code=404, detail="请求的字幕文件尚未生成或不存在")
        
    return FileResponse(target_file, media_type="text/plain", filename=out_name)

@router.get("/tasks")
async def list_tasks():
    tasks = []
    if not os.path.exists(WORKSPACE_DIR):
        return tasks
        
    for task_id in os.listdir(WORKSPACE_DIR):
        task_dir = os.path.join(WORKSPACE_DIR, task_id)
        if not os.path.isdir(task_dir): continue
            
        meta_path = os.path.join(task_dir, "meta.json")
        base_name = task_id[:8] + "..."
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    base_name = json.load(f).get("base_name", base_name)
            except Exception: pass
                
        tasks.append({
            "task_id": task_id, "base_name": base_name, 
            "has_video": any(f.startswith("video.") for f in os.listdir(task_dir)),
            "has_audio": os.path.exists(os.path.join(task_dir, "audio.wav")),
            "has_original_srt": os.path.exists(os.path.join(task_dir, "original.srt")),
            "has_translated_srt": os.path.exists(os.path.join(task_dir, "translated.srt")),
            "created_at": os.path.getmtime(task_dir)
        })
        
    return sorted(tasks, key=lambda x: x["created_at"], reverse=True)

@router.delete("/task/{task_id}")
async def delete_task(task_id: str):
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    if os.path.exists(task_dir):
        shutil.rmtree(task_dir)
        
    global_tasks_status.pop(task_id, None)
    return {"message": "任务删除成功"}