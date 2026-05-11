import os
import json
from fastapi import HTTPException
import asyncio
from ..state import q_extract, q_transcribe, q_translate, global_tasks_status, global_downloading_models, global_cancel_events
from .config_service import test_proxy, config_lock, resolve_active_profile

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

    transcribe_settings = payload.get("transcribe_settings", {})
    if "transcribe" in steps and transcribe_settings.get("engine", "local") == "local":
        model_size = payload.get("model_settings", {}).get("model_size", "large-v2")
        if model_size in global_downloading_models:
            raise HTTPException(status_code=400, detail=f"当前选定的模型 [{model_size}] 正在后台下载中，为防止文件损坏，请等待其下载完成后再启动任务！")

    system_settings = payload.get("system_settings", {})
    proxy_url = system_settings.get("network_proxy", "").strip()
    enable_proxy = system_settings.get("enable_global_proxy", False)
    if enable_proxy and proxy_url:
        await asyncio.to_thread(test_proxy, proxy_url) # 防止阻塞主事件循环

    # 注入激活的 API Profile 配置 (展平化以便 Worker 直接读取)
    if "llm_settings" in payload:
        payload["llm_settings"] = resolve_active_profile(payload["llm_settings"])
    if "online_asr_settings" in payload:
        payload["online_asr_settings"] = resolve_active_profile(payload["online_asr_settings"])

    global_tasks_status[task_id] = { "steps": steps, "current_step": "pending", "config": payload }
    global_cancel_events[task_id] = asyncio.Event()

    if "extract" in steps: global_tasks_status[task_id]["current_step"] = "pending_extract"; await q_extract.put((task_id, payload))
    elif "transcribe" in steps: global_tasks_status[task_id]["current_step"] = "pending_transcribe"; await q_transcribe.put((task_id, payload))
    elif "translate" in steps: global_tasks_status[task_id]["current_step"] = "pending_translate"; await q_translate.put((task_id, payload))

    return {"task_id": task_id, "message": "工作流已加入流水线队列"}

def cancel_task(task_id: str):
    active_states = ["pending_extract", "extracting", "pending_transcribe", "transcribing", "pending_translate", "translating"]
    if task_id in global_tasks_status:
        current_step = global_tasks_status[task_id].get("current_step")
        if current_step in active_states:
            if task_id in global_cancel_events:
                global_cancel_events[task_id].set()
            global_tasks_status[task_id]["current_step"] = "cancelled"

def cancel_all_tasks():
    # 清空队列
    for q in [q_extract, q_transcribe, q_translate]:
        while not q.empty():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                break
    
    active_states = ["pending_extract", "extracting", "pending_transcribe", "transcribing", "pending_translate", "translating"]
    
    # 群发毒丸
    for task_id, cancel_event in global_cancel_events.items():
        if task_id in global_tasks_status:
            current_step = global_tasks_status[task_id].get("current_step")
            if current_step in active_states:
                cancel_event.set()
                global_tasks_status[task_id]["current_step"] = "cancelled"
