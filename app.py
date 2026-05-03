import os
import json
import uuid
import asyncio
import shutil
import urllib.request
import urllib.error
import logging
from typing import Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from core.audio_extractor import extract_audio
from core.whisper_engine import transcribe_audio, unload_model
from core.srt_formatter import generate_srt
from core.translate import run_llm_translation
from core.api_transcribe import run_api_transcription
from faster_whisper import available_models

SUPPORTED_LANGUAGES = {
    "af": "afrikaans", "am": "amharic", "ar": "arabic", "as": "assamese", "az": "azerbaijani", 
    "ba": "bashkir", "be": "belarusian", "bg": "bulgarian", "bn": "bengali", "bo": "tibetan", 
    "br": "breton", "bs": "bosnian", "ca": "catalan", "cs": "czech", "cy": "welsh", 
    "da": "danish", "de": "german", "el": "greek", "en": "english", "es": "spanish", 
    "et": "estonian", "eu": "basque", "fa": "persian", "fi": "finnish", "fo": "faroese", 
    "fr": "french", "gl": "galician", "gu": "gujarati", "ha": "hausa", "haw": "hawaiian", 
    "he": "hebrew", "hi": "hindi", "hr": "croatian", "ht": "haitian creole", "hu": "hungarian", 
    "hy": "armenian", "id": "indonesian", "is": "icelandic", "it": "italian", "ja": "japanese", 
    "jw": "javanese", "ka": "georgian", "kk": "kazakh", "km": "khmer", "kn": "kannada", 
    "ko": "korean", "la": "latin", "lb": "luxembourgish", "ln": "lingala", "lo": "lao", 
    "lt": "lithuanian", "lv": "latvian", "mg": "malagasy", "mi": "maori", "mk": "macedonian", 
    "ml": "malayalam", "mn": "mongolian", "mr": "marathi", "ms": "malay", "mt": "maltese", 
    "my": "myanmar", "ne": "nepali", "nl": "dutch", "nn": "nynorsk", "no": "norwegian", 
    "oc": "occitan", "pa": "punjabi", "pl": "polish", "ps": "pashto", "pt": "portuguese", 
    "ro": "romanian", "ru": "russian", "sa": "sanskrit", "sd": "sindhi", "si": "sinhala", 
    "sk": "slovak", "sl": "slovenian", "sn": "shona", "so": "somali", "sq": "albanian", 
    "sr": "serbian", "su": "sundanese", "sv": "swedish", "sw": "swahili", "ta": "tamil", 
    "te": "telugu", "tg": "tajik", "th": "thai", "tk": "turkmen", "tl": "tagalog", 
    "tr": "turkish", "tt": "tatar", "uk": "ukrainian", "ur": "urdu", "uz": "uzbek", 
    "vi": "vietnamese", "yi": "yiddish", "yo": "yoruba", "zh": "chinese"
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(worker_extract_loop())
    asyncio.create_task(worker_transcribe_loop())
    asyncio.create_task(worker_translate_loop())
    yield

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/api/pipeline/status") == -1

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

app = FastAPI(title="EchoSRT Web API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKSPACE_DIR = os.path.abspath(os.path.join(os.getcwd(), "workspace"))
os.makedirs(WORKSPACE_DIR, exist_ok=True)

def set_global_proxy(proxy_url: str):
    proxy = proxy_url.strip() if proxy_url else ""
    if proxy:
        if proxy.startswith("socks5://"):
            proxy = proxy.replace("socks5://", "socks5h://", 1)
        elif not proxy.startswith("http://") and not proxy.startswith("https://") and not proxy.startswith("socks5h://"):
            proxy = f"http://{proxy}"
        
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy
        os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
        print(f"[*] 已动态应用全局网络代理: {proxy}")
    else:
        for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY"]:
            os.environ.pop(k, None)

try:
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            set_global_proxy(json.load(f).get("system_settings", {}).get("network_proxy", ""))
except Exception: pass

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.locks: Dict[str, asyncio.Lock] = {}
        self.task_states: Dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        self.active_connections[task_id] = websocket
        self.locks[task_id] = asyncio.Lock()

    def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]
        if task_id in self.locks:
            del self.locks[task_id]

    async def send_json(self, data: dict, task_id: str):
        self.task_states[task_id] = data
        
        ws = self.active_connections.get(task_id)
        lock = self.locks.get(task_id)
        if ws and lock:
            try:
                async with lock:
                    await ws.send_json(data)
            except Exception:
                pass

manager = ConnectionManager()

q_extract = asyncio.Queue()
q_transcribe = asyncio.Queue()
q_translate = asyncio.Queue()

global_tasks_status: Dict[str, dict] = {}

@app.get("/api/config")
async def get_config():
    if not os.path.exists("config.json"):
        if os.path.exists("config.example.json"):
            shutil.copy("config.example.json", "config.json")
    
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取配置失败: {str(e)}")

@app.post("/api/config/restore")
async def restore_config():
    if not os.path.exists("config.example.json"):
        raise HTTPException(status_code=404, detail="找不到 config.example.json 默认配置文件")
    
    shutil.copy("config.example.json", "config.json")
    
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取恢复后的配置失败: {str(e)}")

@app.post("/api/config")
async def update_config(payload: dict = Body(...)):
    try:
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        set_global_proxy(payload.get("system_settings", {}).get("network_proxy", ""))
        return {"message": "配置已保存并生效"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")

@app.post("/api/proxy/test")
async def test_proxy(payload: dict = Body(...)):
    import urllib.parse
    import socket
    proxy_url = payload.get("proxy_url", "").strip()
    if not proxy_url:
        return {"status": "ok", "message": "未配置代理"}
        
    try:
        if "://" not in proxy_url:
            proxy_url = f"http://{proxy_url}"
            
        parsed = urllib.parse.urlparse(proxy_url)
        host = parsed.hostname
        port = parsed.port
        
        if not host or not port:
            raise ValueError("代理地址或端口格式无效")
            
        with socket.create_connection((host, port), timeout=3.0):
            pass
            
        return {"status": "ok", "message": "代理服务器连接成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"代理服务器连接失败，请检查配置。({str(e)})")

@app.get("/api/languages")
async def get_languages():
    langs = [{"code": k, "name": v.capitalize()} for k, v in SUPPORTED_LANGUAGES.items()]
    return sorted(langs, key=lambda x: x["name"])

@app.get("/api/models")
async def get_models():
    models = available_models()
    
    standard_models = []
    en_models = []
    distil_models = []
    
    for m in models:
        if "distil" in m:
            distil_models.append(m)
        elif m.endswith(".en"):
            en_models.append(m)
        else:
            standard_models.append(m)
            
    return [
        {"label": "✨ 常规多语言模型 (Standard)", "options": standard_models},
        {"label": "⚡ 蒸馏加速模型 (Distilled)", "options": distil_models},
        {"label": "🇬🇧 纯英文模型 (English Only)", "options": en_models}
    ]

@app.get("/api/llm/models")
async def get_llm_models(api_key: str, base_url: str = "https://api.openai.com/v1"):
    if not api_key:
        raise HTTPException(status_code=400, detail="请先填写 API Key")
    
    base_url = base_url.strip().rstrip("/")
    url = f"{base_url}/models"
    
    req = urllib.request.Request(url)
    req.add_header("accept", "application/json")
    req.add_header("authorization", f"Bearer {api_key}")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            models = data.get("data", [])
            return [m["id"] for m in models if "id" in m]
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        raise HTTPException(status_code=e.code, detail=f"获取失败: {err_msg}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"拉取模型列表异常: {str(e)}")

@app.get("/api/asr/models")
async def get_asr_models(api_key: str, base_url: str = "https://api.openai.com/v1"):
    if not api_key:
        raise HTTPException(status_code=400, detail="请先填写 API Key")
    
    base_url = base_url.strip().rstrip("/")
    url = f"{base_url}/models"
    
    req = urllib.request.Request(url)
    req.add_header("accept", "application/json")
    req.add_header("authorization", f"Bearer {api_key}")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            models = data.get("data", [])
            all_model_ids = [m["id"] for m in models if "id" in m]
            
            asr_keywords = ["whisper", "asr", "audio", "speech", "stt", "sensevoice", "paraformer"]
            filtered_models = [m_id for m_id in all_model_ids if any(kw in m_id.lower() for kw in asr_keywords)]
            
            return filtered_models if filtered_models else all_model_ids
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        raise HTTPException(status_code=e.code, detail=f"获取失败: {err_msg}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"拉取模型列表异常: {str(e)}")

@app.post("/api/upload/{asset_type}")
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

@app.post("/api/task/execute")
async def execute_task(payload: dict = Body(...)):
    task_id = payload.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="缺少 task_id")
        
    steps = payload.get("steps", [])
    if not steps:
        raise HTTPException(status_code=400, detail="未指定执行步骤")

    proxy_url = payload.get("system_settings", {}).get("network_proxy", "").strip()
    if proxy_url:
        import urllib.parse
        import socket
        try:
            test_url = proxy_url if "://" in proxy_url else f"http://{proxy_url}"
            parsed = urllib.parse.urlparse(test_url)
            host = parsed.hostname
            port = parsed.port
            if not host or not port:
                raise ValueError("地址或端口为空")
            
            with socket.create_connection((host, port), timeout=3.0):
                pass
        except Exception as e:
            err_msg = f"连接配置的代理服务器 ({host}:{port}) 失败，请检查或关闭代理开关。({str(e)})"
            print(f"[错误] {err_msg}")
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

@app.websocket("/ws/progress/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await manager.connect(websocket, task_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(task_id)

@app.get("/api/task/{task_id}/status")
async def get_task_status(task_id: str):
    if task_id in manager.task_states:
        return manager.task_states[task_id]
    
    return {"status": "unknown"}

@app.get("/api/pipeline/status")
async def get_pipeline_status():
    return global_tasks_status

@app.get("/api/download/{task_id}")
async def download_srt(task_id: str, type: str = "original"):
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    if not os.path.exists(task_dir):
        raise HTTPException(status_code=404, detail="任务目录不存在")
        
    meta_path = os.path.join(task_dir, "meta.json")
    base_name = "output"
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            base_name = meta.get("base_name", "output")
            
    if type == "translated":
        target_file = os.path.join(task_dir, "translated.srt")
        out_name = f"{base_name}_chs.srt"
    else:
        target_file = os.path.join(task_dir, "original.srt")
        out_name = f"{base_name}.srt"
    
    if not os.path.exists(target_file):
        raise HTTPException(status_code=404, detail="请求的字幕文件尚未生成或不存在")
        
    return FileResponse(target_file, media_type="text/plain", filename=out_name)

@app.get("/api/tasks")
async def list_tasks():
    tasks = []
    if not os.path.exists(WORKSPACE_DIR):
        return tasks
        
    for task_id in os.listdir(WORKSPACE_DIR):
        task_dir = os.path.join(WORKSPACE_DIR, task_id)
        if not os.path.isdir(task_dir):
            continue
            
        meta_path = os.path.join(task_dir, "meta.json")
        base_name = task_id[:8] + "..."
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    base_name = meta.get("base_name", base_name)
            except Exception:
                pass
                
        has_video = any(f.startswith("video.") for f in os.listdir(task_dir))
        has_audio = os.path.exists(os.path.join(task_dir, "audio.wav"))
        has_original = os.path.exists(os.path.join(task_dir, "original.srt"))
        has_translated = os.path.exists(os.path.join(task_dir, "translated.srt"))
        
        created_at = os.path.getmtime(task_dir)
        
        tasks.append({"task_id": task_id, "base_name": base_name, "has_video": has_video, "has_audio": has_audio, "has_original_srt": has_original, "has_translated_srt": has_translated, "created_at": created_at})
        
    return sorted(tasks, key=lambda x: x["created_at"], reverse=True)

@app.delete("/api/task/{task_id}")
async def delete_task(task_id: str):
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    if os.path.exists(task_dir):
        shutil.rmtree(task_dir)
        
    manager.task_states.pop(task_id, None)
    global_tasks_status.pop(task_id, None)
    return {"message": "任务删除成功"}

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

app.mount("/", StaticFiles(directory=os.path.join(os.getcwd(), "frontend"), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False, log_level="warning")
