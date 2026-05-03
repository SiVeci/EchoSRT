import os
import asyncio

from ..state import q_extract, q_transcribe, q_translate, global_tasks_status
from ..ws_manager import manager

from core.audio_extractor import extract_audio

WORKSPACE_DIR = os.path.abspath(os.path.join(os.getcwd(), "workspace"))

async def worker_extract_loop():
    loop = asyncio.get_running_loop()
    while True:
        task_id, config_payload = await q_extract.get()
        steps = config_payload.get("steps", [])
        task_dir = os.path.join(WORKSPACE_DIR, task_id)
        
        if task_id in global_tasks_status:
            global_tasks_status[task_id]["current_step"] = "extracting"

        try:
            video_files = [f for f in os.listdir(task_dir) if f.startswith("video.")]
            if not video_files:
                raise Exception("缺少视频源文件，无法执行音频提取。请先上传视频。")
            
            video_path = os.path.join(task_dir, video_files[0])
            audio_path = os.path.join(task_dir, "audio.wav")
            ffmpeg_settings = config_payload.get("ffmpeg_settings", {})
            
            def audio_progress_callback(extracted_time):
                msg = {"status": "processing", "step": "extract_audio", "extracted_time": extracted_time}
                asyncio.run_coroutine_threadsafe(manager.send_json(msg, task_id), loop)
                
            await manager.send_json({"status": "processing", "step": "extract_audio", "message": "正在提取音频..."}, task_id)
            await loop.run_in_executor(None, extract_audio, video_path, audio_path, audio_progress_callback, ffmpeg_settings)

            if "transcribe" in steps:
                if task_id in global_tasks_status: global_tasks_status[task_id]["current_step"] = "pending_transcribe"
                await q_transcribe.put((task_id, config_payload))
            elif "translate" in steps:
                if task_id in global_tasks_status: global_tasks_status[task_id]["current_step"] = "pending_translate"
                await q_translate.put((task_id, config_payload))
            else:
                if task_id in global_tasks_status: global_tasks_status[task_id]["current_step"] = "completed"
                await manager.send_json({"status": "completed", "step": "done", "message": "任务流水线执行完毕！"}, task_id)

        except Exception as e:
            print(f"[提取车间错误] {e}")
            if task_id in global_tasks_status: global_tasks_status[task_id]["current_step"] = "error"
            await manager.send_json({"status": "error", "message": f"音频提取失败: {str(e)}"}, task_id)
        finally:
            q_extract.task_done()