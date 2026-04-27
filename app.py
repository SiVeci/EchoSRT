import os
import json
import uuid
import asyncio
import shutil
import urllib.request
import urllib.error
from typing import Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from core.audio_extractor import extract_audio
from core.whisper_engine import transcribe_audio, unload_model
from core.srt_formatter import generate_srt
from core.translate import run_llm_translation
from core.api_transcribe import run_api_transcription
from faster_whisper import available_models

# Whisper 支持的 99 种语言映射表
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

app = FastAPI(title="EchoSRT Web API")

# 配置 CORS，允许前端跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中建议替换为前端的具体地址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 统一的工作区目录，存放上传的视频、临时音频和生成的字幕
WORKSPACE_DIR = os.path.abspath(os.path.join(os.getcwd(), "workspace"))
os.makedirs(WORKSPACE_DIR, exist_ok=True)

# ==========================================
# WebSocket 连接管理器
# ==========================================
class ConnectionManager:
    def __init__(self):
        # 存放 task_id 对应的 WebSocket 连接
        self.active_connections: Dict[str, WebSocket] = {}
        # 为每个 WebSocket 添加一个异步锁，防止并发发送数据导致底层协议崩溃
        self.locks: Dict[str, asyncio.Lock] = {}

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
        """向指定任务的前端推送 JSON 格式数据（加锁保证线程安全）"""
        ws = self.active_connections.get(task_id)
        lock = self.locks.get(task_id)
        if ws and lock:
            try:
                async with lock:
                    await ws.send_json(data)
            except Exception:
                pass # 忽略因前端主动断开而导致的发送异常

manager = ConnectionManager()

# ==========================================
# API 路由
# ==========================================

@app.get("/api/config")
async def get_config():
    """获取默认的参数配置"""
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
    """恢复默认配置 (从 config.example.json 覆盖 config.json)"""
    if not os.path.exists("config.example.json"):
        raise HTTPException(status_code=404, detail="找不到 config.example.json 默认配置文件")
    
    shutil.copy("config.example.json", "config.json")
    
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取恢复后的配置失败: {str(e)}")

@app.get("/api/languages")
async def get_languages():
    """获取 Whisper 支持的所有语言列表"""
    langs = [{"code": k, "name": v.capitalize()} for k, v in SUPPORTED_LANGUAGES.items()]
    return sorted(langs, key=lambda x: x["name"])

@app.get("/api/models")
async def get_models():
    """动态获取 faster-whisper 支持的所有模型列表并分组"""
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
    """从大模型供应商处拉取支持对话的模型列表"""
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
    """从云端语音识别 API 供应商处拉取支持的模型列表"""
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
            
            # 本地过滤：从返回的通用模型池中，筛选出包含常见语音识别关键字的模型
            asr_keywords = ["whisper", "asr", "audio", "speech", "stt", "sensevoice", "paraformer"]
            filtered_models = [m_id for m_id in all_model_ids if any(kw in m_id.lower() for kw in asr_keywords)]
            
            # 防呆设计：如果按关键字没有匹配到任何模型，则回退返回所有模型
            return filtered_models if filtered_models else all_model_ids
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        raise HTTPException(status_code=e.code, detail=f"获取失败: {err_msg}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"拉取模型列表异常: {str(e)}")

@app.post("/api/upload/{asset_type}")
async def upload_asset(asset_type: str, file: UploadFile = File(...), task_id: str = Form(None)):
    """接收前端上传的媒体资产 (video, audio, srt)"""
    if not task_id:
        task_id = str(uuid.uuid4())
    
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    # 处理 metadata 以保留原始文件名
    meta_path = os.path.join(task_dir, "meta.json")
    meta_data = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta_data = json.load(f)

    # 始终以用户最初上传的文件名作为最终产物的 Base Name
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
    
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, ensure_ascii=False)
        
    return {"task_id": task_id, "filename": file.filename, "message": f"{asset_type} 上传成功"}

@app.post("/api/task/execute")
async def execute_task(background_tasks: BackgroundTasks, payload: dict = Body(...)):
    """接收配置并按步骤执行工作流任务"""
    task_id = payload.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="缺少 task_id")
        
    # 将前端传来的新参数保存回 config.json
    config_to_save = {k: v for k, v in payload.items() if k not in ["task_id", "steps"]}
    try:
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config_to_save, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[警告] 无法保存最新配置到 config.json: {e}")

    background_tasks.add_task(run_pipeline_task, task_id, payload)
    return {"task_id": task_id, "message": "工作流已启动"}

@app.websocket("/ws/progress/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket 接口：前端连入用于监听实时进度"""
    await manager.connect(websocket, task_id)
    try:
        # 保持连接不断开，等待前端主动断开或任务完成
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(task_id)

@app.get("/api/download/{task_id}")
async def download_srt(task_id: str, type: str = "original"):
    """下载生成的字幕文件 (type=original|translated)"""
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
    """获取所有工作区历史任务列表"""
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
                
        # 检查各阶段资产是否就绪
        has_video = any(f.startswith("video.") for f in os.listdir(task_dir))
        has_audio = os.path.exists(os.path.join(task_dir, "audio.wav"))
        has_original = os.path.exists(os.path.join(task_dir, "original.srt"))
        has_translated = os.path.exists(os.path.join(task_dir, "translated.srt"))
        
        created_at = os.path.getmtime(task_dir)
        
        tasks.append({"task_id": task_id, "base_name": base_name, "has_video": has_video, "has_audio": has_audio, "has_original_srt": has_original, "has_translated_srt": has_translated, "created_at": created_at})
        
    return sorted(tasks, key=lambda x: x["created_at"], reverse=True)

@app.delete("/api/task/{task_id}")
async def delete_task(task_id: str):
    """删除指定的任务空间"""
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    if os.path.exists(task_dir):
        shutil.rmtree(task_dir)
    return {"message": "任务删除成功"}

# ==========================================
# 后台任务逻辑
# ==========================================

def get_hf_repo_id(model_size: str) -> str:
    """推导 Hugging Face 上的完整仓库名称"""
    if "distil" in model_size:
        return f"Systran/faster-distil-whisper-{model_size.replace('distil-', '')}"
    return f"Systran/faster-whisper-{model_size}"

def get_folder_size(folder_path: str) -> int:
    """计算文件夹总字节数，忽略软链接，只计算真实的 blobs"""
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
    """后台监控模型下载进度的守护任务 (精简版: 仅监控当前模型的缓存文件夹)"""
    repo_id = get_hf_repo_id(model_size)
    repo_folder_name = f"models--{repo_id.replace('/', '--')}"
    target_folder = os.path.join(os.getcwd(), download_root, repo_folder_name)
    try:
        while True:
            current_size = await asyncio.to_thread(get_folder_size, target_folder)
            mb_size = current_size / (1024 * 1024)
            
            # 只发送体积进度数据，不附带 message 字段，避免前端疯狂刷新日志行
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

# 任务并发计数与空闲计时器
active_tasks_count = 0
idle_timer_task = None

async def auto_unload_timer():
    """空闲计时器：等待一定时间无任务后自动卸载模型"""
    try:
        # 设置空闲超时时间，例如 300秒 (5分钟)
        await asyncio.sleep(300)
        print("[*] 系统空闲已达 5 分钟，执行自动清理...")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, unload_model)
    except asyncio.CancelledError:
        # 倒计时被取消，说明期间有新任务进来了，无需任何操作
        pass

async def run_pipeline_task(task_id: str, config_payload: dict):
    """
    真正的模块化流水线：根据 steps 参数动态调度执行节点
    """
    global active_tasks_count, idle_timer_task
    loop = asyncio.get_running_loop()
    
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    steps = config_payload.get("steps", [])
    
    active_tasks_count += 1
    if idle_timer_task is not None:
        idle_timer_task.cancel()
        idle_timer_task = None

    try:
        if not os.path.exists(task_dir):
            raise Exception("任务空间目录不存在。")
            
        # ==========================================
        # 阶段 1: 音频提取 (FFmpeg)
        # ==========================================
        if "extract" in steps:
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

        # ==========================================
        # 阶段 2: 语音识别 (Whisper)
        # ==========================================
        if "transcribe" in steps:
            audio_path = os.path.join(task_dir, "audio.wav")
            if not os.path.exists(audio_path):
                raise Exception("缺少 audio.wav 文件，无法执行语音识别。请先执行提取音频。")
                
            output_srt = os.path.join(task_dir, "original.srt")
            transcribe_settings = config_payload.get("transcribe_settings", {})
            engine = transcribe_settings.get("engine", "local")
            
            if engine == "api":
                # ==============================
                # 分支 A: 云端 API 识别引擎
                # ==============================
                online_asr_settings = config_payload.get("online_asr_settings", {})
                
                def api_progress_callback(msg_text):
                    msg = {"status": "processing", "step": "transcribing", "message": msg_text}
                    asyncio.run_coroutine_threadsafe(manager.send_json(msg, task_id), loop)
                
                await loop.run_in_executor(None, run_api_transcription, audio_path, output_srt, online_asr_settings, api_progress_callback)
                
            else:
                # ==============================
                # 分支 B: 本地 faster-whisper 引擎
                # ==============================
                model_settings = config_payload.get("model_settings", {})
                vad_settings = config_payload.get("vad_settings", {})
                
                await manager.send_json({"status": "processing", "step": "downloading", "message": "正在读取或下载模型..."}, task_id)
                monitor_task = asyncio.create_task(monitor_download(task_id, model_settings.get("download_root", "models"), model_settings.get("model_size", "large-v2")))

                try:
                    segments = await loop.run_in_executor(None, transcribe_audio, audio_path, model_settings, transcribe_settings, vad_settings)
                finally:
                    monitor_task.cancel()
                    
                await manager.send_json({"status": "processing", "step": "transcribing", "message": "模型加载完毕，开始语音识别..."}, task_id)

                def progress_callback(start_time, end_time, text):
                    msg = {"status": "processing", "step": "transcribing", "progress": f"{start_time} -> {end_time}", "text": text}
                    asyncio.run_coroutine_threadsafe(manager.send_json(msg, task_id), loop)
                    
                await loop.run_in_executor(None, generate_srt, segments, output_srt, progress_callback)

        # ==========================================
        # 阶段 3: LLM 智能翻译 (DeepSeek)
        # ==========================================
        if "translate" in steps:
            input_srt = os.path.join(task_dir, "original.srt")
            if not os.path.exists(input_srt):
                raise Exception("缺少 original.srt 生肉字幕，无法执行翻译。请先执行识别或上传外置字幕。")
                
            output_translated = os.path.join(task_dir, "translated.srt")
            llm_config = config_payload.get("llm_settings", {})
            
            def translate_progress_callback(msg_text):
                msg = {"status": "processing", "step": "translating", "message": msg_text}
                asyncio.run_coroutine_threadsafe(manager.send_json(msg, task_id), loop)
                
            await manager.send_json({"status": "processing", "step": "translating", "message": "正在请求大模型翻译..."}, task_id)
            await loop.run_in_executor(None, run_llm_translation, input_srt, output_translated, llm_config, translate_progress_callback)

        # 全局完成
        await manager.send_json({"status": "completed", "step": "done", "message": "工作流执行完毕！"}, task_id)
        
    except Exception as e:
        print(f"[错误] 工作流任务异常: {e}")
        await manager.send_json({"status": "error", "message": str(e)}, task_id)
    finally:
        # 注意：取消了自动删除源文件和临时音频的逻辑。它们将驻留在任务空间中，支持分步重试。
        active_tasks_count -= 1
        if active_tasks_count <= 0:
            active_tasks_count = 0
            idle_timer_task = asyncio.create_task(auto_unload_timer())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)