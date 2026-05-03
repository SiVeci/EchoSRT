import os
import asyncio

from .state import q_extract, q_transcribe, q_translate, global_tasks_status
from .ws_manager import manager

from core.audio_extractor import extract_audio
from core.whisper_engine import transcribe_audio, unload_model
from core.srt_formatter import generate_srt
from core.translate import run_llm_translation
from core.api_transcribe import run_api_transcription

WORKSPACE_DIR = os.path.abspath(os.path.join(os.getcwd(), "workspace"))

def get_hf_repo_id(model_size: str) -> str:
    if "distil" in model_size:
        return f"Systran/faster-distil-whisper-{model_size.replace('distil-', '')}"
    return f"Systran/faster-whisper-{model_size}"

def get_folder_size(folder_path: str) -> int:
    total_size = 0
    if not os.path.exists(folder_path):
        return 0
    for dirpath, _, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size

async def monitor_download(task_id: str, download_root: str, model_size: str):
    repo_id = get_hf_repo_id(model_size)
    repo_folder_name = f"models--{repo_id.replace('/', '--')}"
    target_folder = os.path.join(os.getcwd(), download_root, repo_folder_name)
    try:
        while True:
            current_size = await asyncio.to_thread(get_folder_size, target_folder)
            mb_size = current_size / (1024 * 1024)
            
            msg = {
                "status": "processing", 
                "step": "downloading", 
                "downloaded_mb": round(mb_size, 1)
            }
            
            await manager.send_json(msg, task_id)
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[监控线程异常] {e}")

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

async def worker_transcribe_loop():
    loop = asyncio.get_running_loop()
    while True:
        try:
            task_id, config_payload = await asyncio.wait_for(q_transcribe.get(), timeout=300.0)
        except asyncio.TimeoutError:
            await loop.run_in_executor(None, unload_model)
            continue

        steps = config_payload.get("steps", [])
        task_dir = os.path.join(WORKSPACE_DIR, task_id)
        
        if task_id in global_tasks_status:
            global_tasks_status[task_id]["current_step"] = "transcribing"

        try:
            audio_path = os.path.join(task_dir, "audio.wav")
            if not os.path.exists(audio_path):
                raise Exception("缺少 audio.wav 文件，无法执行语音识别。")
                
            output_srt = os.path.join(task_dir, "original.srt")
            transcribe_settings = config_payload.get("transcribe_settings", {})
            system_settings = config_payload.get("system_settings", {})
            engine = transcribe_settings.get("engine", "local")
            
            if engine == "api":
                online_asr_settings = config_payload.get("online_asr_settings", {})
                def api_progress_callback(msg_text):
                    msg = {"status": "processing", "step": "transcribing", "message": msg_text}
                    asyncio.run_coroutine_threadsafe(manager.send_json(msg, task_id), loop)
                await loop.run_in_executor(None, run_api_transcription, audio_path, output_srt, online_asr_settings, system_settings, api_progress_callback)
                
            else:
                model_settings = config_payload.get("model_settings", {})
                vad_settings = config_payload.get("vad_settings", {})
                
                await manager.send_json({"status": "processing", "step": "downloading", "message": "正在读取或下载模型..."}, task_id)
                monitor_task = asyncio.create_task(monitor_download(task_id, model_settings.get("download_root", "models"), model_settings.get("model_size", "large-v2")))

                try:
                    segments = await loop.run_in_executor(None, transcribe_audio, audio_path, model_settings, transcribe_settings, vad_settings, system_settings)
                finally:
                    monitor_task.cancel()
                    
                await manager.send_json({"status": "processing", "step": "transcribing", "message": "模型加载完毕，开始语音识别..."}, task_id)

                def progress_callback(start_time, end_time, text):
                    msg = {"status": "processing", "step": "transcribing", "progress": f"{start_time} -> {end_time}", "text": text}
                    asyncio.run_coroutine_threadsafe(manager.send_json(msg, task_id), loop)
                    
                await loop.run_in_executor(None, generate_srt, segments, output_srt, progress_callback)

            if "translate" in steps:
                if task_id in global_tasks_status: global_tasks_status[task_id]["current_step"] = "pending_translate"
                await q_translate.put((task_id, config_payload))
            else:
                if task_id in global_tasks_status: global_tasks_status[task_id]["current_step"] = "completed"
                await manager.send_json({"status": "completed", "step": "done", "message": "任务流水线执行完毕！"}, task_id)

        except Exception as e:
            print(f"[识别车间错误] {e}")
            if task_id in global_tasks_status: global_tasks_status[task_id]["current_step"] = "error"
            await manager.send_json({"status": "error", "message": f"语音识别失败: {str(e)}"}, task_id)
        finally:
            q_transcribe.task_done()

async def worker_translate_loop():
    loop = asyncio.get_running_loop()
    while True:
        task_id, config_payload = await q_translate.get()
        task_dir = os.path.join(WORKSPACE_DIR, task_id)
        
        if task_id in global_tasks_status:
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
                asyncio.run_coroutine_threadsafe(manager.send_json(msg, task_id), loop)
                
            await manager.send_json({"status": "processing", "step": "translating", "message": "正在并发请求大模型翻译..."}, task_id)
            await run_llm_translation(input_srt, output_translated, llm_config, system_config, translate_progress_callback)

            if task_id in global_tasks_status: global_tasks_status[task_id]["current_step"] = "completed"
            await manager.send_json({"status": "completed", "step": "done", "message": "全量任务流水线完美收官！"}, task_id)

        except Exception as e:
            print(f"[翻译车间错误] {e}")
            if task_id in global_tasks_status: global_tasks_status[task_id]["current_step"] = "error"
            await manager.send_json({"status": "error", "message": f"智能翻译失败: {str(e)}"}, task_id)
        finally:
            q_translate.task_done()