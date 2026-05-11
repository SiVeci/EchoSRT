import os
import asyncio

from ..state import q_translate, global_tasks_status, global_cancel_events
from ..ws_manager import manager
import json

from core.translate import run_llm_translation

WORKSPACE_DIR = os.path.abspath(os.path.join(os.getcwd(), "workspace"))

async def process_translate_task(task_id, config_payload, loop):
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    
    if task_id in global_cancel_events and global_cancel_events[task_id].is_set():
        return

    if task_id in global_tasks_status:
        if global_tasks_status[task_id].get("current_step") == "translating":
            print(f"[翻译车间] 任务 {task_id} 已在处理中，忽略并发抢占。")
            return
        global_tasks_status[task_id]["current_step"] = "translating"

    try:
        input_srt = os.path.join(task_dir, "original.srt")
        if not os.path.exists(input_srt):
            raise Exception("缺少 original.srt 生肉字幕，无法执行翻译。")
            
        output_translated = os.path.join(task_dir, "translated.srt")
        llm_config = config_payload.get("llm_settings", {})
        system_config = config_payload.get("system_settings", {})
        
        def translate_progress_callback(msg_text):
            msg = {"status": "processing", "step": "translating", "message": msg_text}
            loop.create_task(manager.send_json(msg, task_id))
            
        await manager.send_json({"status": "processing", "step": "translating", "message": "正在并发请求大模型翻译..."}, task_id)
        
        cancel_event = global_cancel_events.get(task_id)
        await run_llm_translation(input_srt, output_translated, llm_config, system_config, translate_progress_callback, cancel_event)

        # [薛定谔修复] 将当时使用的目标语种固化到该任务专属的 meta.json 中
        target_lang = llm_config.get("target_language", "zh")
        meta_path = os.path.join(task_dir, "meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f: meta_data = json.load(f)
                meta_data["translated_language"] = target_lang
                with open(meta_path, "w", encoding="utf-8") as f: json.dump(meta_data, f, ensure_ascii=False)
            except Exception: pass

        if task_id in global_tasks_status: global_tasks_status[task_id]["current_step"] = "completed"
        await manager.send_json({"status": "completed", "step": "done", "message": "全量任务流水线完美收官！"}, task_id)

    except asyncio.CancelledError:
        print(f"[翻译车间] 任务 {task_id} 被手动中断")
        err_translated_path = os.path.join(task_dir, "translated.srt")
        if os.path.exists(err_translated_path):
            try: os.remove(err_translated_path)
            except: pass
        await manager.send_json({"status": "error", "message": "任务已被手动中断"}, task_id)

    except Exception as e:
        print(f"[翻译车间错误] {e}")
        # 清道夫：如果出错，清理可能残留的损坏文件
        err_translated_path = os.path.join(task_dir, "translated.srt")
        if os.path.exists(err_translated_path):
            try: os.remove(err_translated_path)
            except: pass
        if task_id in global_tasks_status: global_tasks_status[task_id]["current_step"] = "error"
        await manager.send_json({"status": "error", "message": f"智能翻译失败: {str(e)}"}, task_id)

async def worker_translate_loop():
    loop = asyncio.get_running_loop()
    while True:
        task_id, config_payload = await q_translate.get()
        try:
            await process_translate_task(task_id, config_payload, loop)
        finally:
            q_translate.task_done()