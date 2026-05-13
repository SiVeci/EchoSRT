import os
import json
from fastapi import HTTPException
import asyncio
from ..state import q_extract, q_transcribe, q_translate, global_tasks_status, global_downloading_models, global_cancel_events, update_task_status, get_task_status
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

    task_status = await get_task_status(task_id)
    current_status = task_status.get("current_step")
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

    await update_task_status(task_id, { "steps": steps, "current_step": "pending", "config": payload })
    global_cancel_events[task_id] = asyncio.Event()

    if "extract" in steps: 
        await update_task_status(task_id, {"current_step": "pending_extract"})
        await q_extract.put((task_id, payload))
    elif "transcribe" in steps: 
        await update_task_status(task_id, {"current_step": "pending_transcribe"})
        await q_transcribe.put((task_id, payload))
    elif "translate" in steps: 
        await update_task_status(task_id, {"current_step": "pending_translate"})
        await q_translate.put((task_id, payload))

    return {"task_id": task_id, "message": "工作流已加入流水线队列"}

async def retry_task(task_id: str):
    """手动重试异常中断的任务，尝试从断点恢复"""
    task_id = os.path.basename(str(task_id).replace("\\", "/"))
    task_status = await get_task_status(task_id)
    if not task_status:
        raise HTTPException(status_code=404, detail="任务状态丢失，无法重试。")
    
    current_step = task_status.get("current_step")
    if current_step in ["pending_extract", "extracting", "pending_transcribe", "transcribing", "pending_translate", "translating"]:
        raise HTTPException(status_code=400, detail="任务已在执行队列中，请勿重复重试。")

    # 优先恢复 interrupted_step，如果不存在则尝试从 current_step 恢复（针对 error 状态）
    step_to_resume = task_status.get("interrupted_step") or current_step
    if not step_to_resume or step_to_resume in ["completed", "cancelled"]:
        raise HTTPException(status_code=400, detail="该任务当前状态不支持重试。")

    config_payload = task_status.get("config", {})
    if not config_payload:
        raise HTTPException(status_code=400, detail="任务配置丢失，无法恢复执行。")

    # 重置取消事件
    global_cancel_events[task_id] = asyncio.Event()

    # 判定恢复点
    if step_to_resume in ["pending_extract", "extracting"]:
        await update_task_status(task_id, {"current_step": "pending_extract"})
        await q_extract.put((task_id, config_payload))
    elif step_to_resume in ["pending_transcribe", "transcribing"]:
        await update_task_status(task_id, {"current_step": "pending_transcribe"})
        await q_transcribe.put((task_id, config_payload))
    elif step_to_resume in ["pending_translate", "translating"]:
        await update_task_status(task_id, {"current_step": "pending_translate"})
        await q_translate.put((task_id, config_payload))
    else:
        # 如果处于 error 且没有明确的步骤信息，默认从头开始（如果有 extract 步骤）
        steps = config_payload.get("steps", [])
        if "extract" in steps:
            await update_task_status(task_id, {"current_step": "pending_extract"})
            await q_extract.put((task_id, config_payload))
        elif "transcribe" in steps:
            await update_task_status(task_id, {"current_step": "pending_transcribe"})
            await q_transcribe.put((task_id, config_payload))
        elif "translate" in steps:
            await update_task_status(task_id, {"current_step": "pending_translate"})
            await q_translate.put((task_id, config_payload))

    return {"task_id": task_id, "message": "任务已重新加入流水线"}

async def cancel_task(task_id: str):
    active_states = ["pending_extract", "extracting", "pending_transcribe", "transcribing", "pending_translate", "translating"]
    task_status = await get_task_status(task_id)
    if task_status:
        current_step = task_status.get("current_step")
        if current_step in active_states:
            if task_id in global_cancel_events:
                global_cancel_events[task_id].set()
            await update_task_status(task_id, {"current_step": "cancelled"})

async def cancel_all_tasks():
    # 清空队列
    for q in [q_extract, q_transcribe, q_translate]:
        while not q.empty():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                break
    
    active_states = ["pending_extract", "extracting", "pending_transcribe", "transcribing", "pending_translate", "translating"]
    
    # 群发毒丸
    for task_id, cancel_event in list(global_cancel_events.items()):
        task_status = await get_task_status(task_id)
        if task_status:
            current_step = task_status.get("current_step")
            if current_step in active_states:
                cancel_event.set()
                await update_task_status(task_id, {"current_step": "cancelled"})
