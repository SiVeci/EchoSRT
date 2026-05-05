import os
import json
from fastapi import HTTPException
import asyncio
from ..state import q_extract, q_transcribe, q_translate, global_tasks_status
from .config_service import test_proxy, config_lock

async def dispatch_task(payload: dict):
    task_id = payload.get("task_id")
    if not task_id: raise HTTPException(status_code=400, detail="缺少 task_id")
    
    # 彻底过滤路径穿透字符，防止恶意伪造
    task_id = os.path.basename(str(task_id).replace("\\", "/"))
    if not task_id: raise HTTPException(status_code=400, detail="无效的 task_id")
    payload["task_id"] = task_id
    
    steps = payload.get("steps", [])
    if not steps: raise HTTPException(status_code=400, detail="未指定执行步骤")

    current_status = global_tasks_status.get(task_id, {}).get("current_step")
    if current_status in ["pending_extract", "extracting", "pending_transcribe", "transcribing", "pending_translate", "translating"]:
        raise HTTPException(status_code=400, detail="该任务已在执行队列中，请勿重复下发。")

    system_settings = payload.get("system_settings", {})
    proxy_url = system_settings.get("network_proxy", "").strip()
    enable_proxy = system_settings.get("enable_global_proxy", False)
    if enable_proxy and proxy_url:
        await asyncio.to_thread(test_proxy, proxy_url) # 防止阻塞主事件循环

    config_to_save = {k: v for k, v in payload.items() if k not in ["task_id", "steps"]}
    
    def _save_config():
        os.makedirs("config", exist_ok=True)
        with open("config/config.json", "w", encoding="utf-8") as f: json.dump(config_to_save, f, indent=2, ensure_ascii=False)
        
    async with config_lock:
        try: await asyncio.to_thread(_save_config)
        except Exception as e: print(f"[警告] 无法保存最新配置到 config/config.json: {e}")

    global_tasks_status[task_id] = { "steps": steps, "current_step": "pending", "config": payload }

    if "extract" in steps: global_tasks_status[task_id]["current_step"] = "pending_extract"; await q_extract.put((task_id, payload))
    elif "transcribe" in steps: global_tasks_status[task_id]["current_step"] = "pending_transcribe"; await q_transcribe.put((task_id, payload))
    elif "translate" in steps: global_tasks_status[task_id]["current_step"] = "pending_translate"; await q_translate.put((task_id, payload))

    return {"task_id": task_id, "message": "工作流已加入流水线队列"}