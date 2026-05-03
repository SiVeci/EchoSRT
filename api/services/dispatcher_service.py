import os
import json
from fastapi import HTTPException
from ..state import q_extract, q_transcribe, q_translate, global_tasks_status
from .config_service import test_proxy

async def dispatch_task(payload: dict):
    task_id = payload.get("task_id")
    if not task_id: raise HTTPException(status_code=400, detail="缺少 task_id")
        
    steps = payload.get("steps", [])
    if not steps: raise HTTPException(status_code=400, detail="未指定执行步骤")

    proxy_url = payload.get("system_settings", {}).get("network_proxy", "").strip()
    if proxy_url:
        test_proxy(proxy_url) # 复用配置服务中的连通性测试逻辑

    config_to_save = {k: v for k, v in payload.items() if k not in ["task_id", "steps"]}
    try:
        os.makedirs("config", exist_ok=True)
        with open("config/config.json", "w", encoding="utf-8") as f: json.dump(config_to_save, f, indent=2, ensure_ascii=False)
    except Exception as e: print(f"[警告] 无法保存最新配置到 config/config.json: {e}")

    global_tasks_status[task_id] = { "steps": steps, "current_step": "pending", "config": payload }

    if "extract" in steps: global_tasks_status[task_id]["current_step"] = "pending_extract"; await q_extract.put((task_id, payload))
    elif "transcribe" in steps: global_tasks_status[task_id]["current_step"] = "pending_transcribe"; await q_transcribe.put((task_id, payload))
    elif "translate" in steps: global_tasks_status[task_id]["current_step"] = "pending_translate"; await q_translate.put((task_id, payload))

    return {"task_id": task_id, "message": "工作流已加入流水线队列"}