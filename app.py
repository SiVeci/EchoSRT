import os
import json
import uuid
import asyncio
import shutil
from typing import Dict, Any
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from core.audio_extractor import extract_audio
from core.whisper_engine import transcribe_audio, unload_model
from core.srt_formatter import generate_srt
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

app = FastAPI(title="AutoSRT Web API")

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

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """接收前端上传的视频文件"""
    task_id = str(uuid.uuid4())
    
    # 为每个任务创建独立的文件夹
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    video_path = os.path.join(task_dir, file.filename)
    
    # 保存文件到专属任务工作区
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"task_id": task_id, "filename": file.filename, "message": "文件上传成功"}

@app.post("/api/transcribe")
async def start_transcribe(background_tasks: BackgroundTasks, payload: dict = Body(...)):
    """接收参数并启动后台转录任务"""
    task_id = payload.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="缺少 task_id")
        
    # 将前端传来的新参数保存回 config.json（剔除掉单次任务的 task_id）
    config_to_save = {k: v for k, v in payload.items() if k != "task_id"}
    try:
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config_to_save, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[警告] 无法保存最新配置到 config.json: {e}")

    # 将具体的耗时逻辑放入后台任务，当前请求立即返回
    background_tasks.add_task(run_transcription_task, task_id, payload)
    return {"task_id": task_id, "message": "转录任务已启动"}

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
async def download_srt(task_id: str):
    """下载最终生成的 SRT 字幕文件"""
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    if not os.path.exists(task_dir):
        raise HTTPException(status_code=404, detail="任务目录不存在")
        
    # 在任务专属目录中查找 srt 文件
    srt_files = [f for f in os.listdir(task_dir) if f.endswith(".srt")]
    if not srt_files:
        raise HTTPException(status_code=404, detail="字幕文件尚未生成或不存在")
    
    srt_filename = srt_files[0]
    srt_path = os.path.join(task_dir, srt_filename)
    
    return FileResponse(srt_path, media_type="text/plain", filename=srt_filename)

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

async def run_transcription_task(task_id: str, config_payload: dict):
    """
    真实的转录调度流程，使用 run_in_executor 防止阻塞主事件循环
    """
    global active_tasks_count, idle_timer_task
    loop = asyncio.get_running_loop()
    
    task_dir = os.path.join(WORKSPACE_DIR, task_id)
    temp_audio_path = os.path.join(task_dir, "temp.wav")
    
    # 任务开始：增加并发计数，并随时打断（取消）清理模型的倒计时
    active_tasks_count += 1
    if idle_timer_task is not None:
        idle_timer_task.cancel()
        idle_timer_task = None

    try:
        # 查找该任务目录下的视频文件
        if not os.path.exists(task_dir):
            raise Exception("任务目录丢失。")
            
        video_files = [f for f in os.listdir(task_dir) if not f.endswith(".wav") and not f.endswith(".srt")]
        if not video_files:
            raise Exception("在工作区中未找到对应的视频文件，请重新上传。")
            
        original_filename = video_files[0]
        video_path = os.path.join(task_dir, original_filename)

        # 生成的 srt 直接使用原视频的纯粹名称
        base_name = os.path.splitext(original_filename)[0]
        srt_path = os.path.join(task_dir, f"{base_name}.srt")

        # 1. 提取音频阶段
        def audio_progress_callback(extracted_time):
            msg = {
                "status": "processing", 
                "step": "extract_audio", 
                "extracted_time": extracted_time
            }
            asyncio.run_coroutine_threadsafe(manager.send_json(msg, task_id), loop)
            
        await manager.send_json({"status": "processing", "step": "extract_audio", "message": "正在提取音频..."}, task_id)
        await loop.run_in_executor(None, extract_audio, video_path, temp_audio_path, audio_progress_callback)
        
        # 2. 加载模型与识别阶段
        model_settings = config_payload.get("model_settings", {})
        transcribe_settings = config_payload.get("transcribe_settings", {})
        vad_settings = config_payload.get("vad_settings", {})

        model_size = model_settings.get("model_size", "large-v2")
        download_root = model_settings.get("download_root", "models")
        
        # 发送一次性的日志提示
        await manager.send_json({"status": "processing", "step": "downloading", "message": "正在读取或下载模型... (请耐心等待)"}, task_id)
        monitor_task = asyncio.create_task(monitor_download(task_id, download_root, model_size))

        try:
            segments = await loop.run_in_executor(
                None,
                transcribe_audio,
                temp_audio_path,
                model_settings,
                transcribe_settings,
                vad_settings
            )
        finally:
            monitor_task.cancel()  # 只要模型加载动作一结束，立刻终止监控进程
            
        await manager.send_json({"status": "processing", "step": "transcribing", "message": "模型加载完毕，开始语音识别..."}, task_id)

        # 3. 进度回调函数：在子线程中被调用，用来把进度扔回主线程的 WebSocket 发送任务中
        def progress_callback(start_time, end_time, text):
            msg = {
                "status": "processing",
                "step": "transcribing",
                "progress": f"{start_time} -> {end_time}",
                "text": text
            }
            asyncio.run_coroutine_threadsafe(manager.send_json(msg, task_id), loop)
            
        # 4. 生成 SRT 文件并推送进度
        await loop.run_in_executor(None, generate_srt, segments, srt_path, progress_callback)
            
        # 5. 通知前端全部完成
        await manager.send_json({"status": "completed", "step": "done", "message": "字幕生成完毕！"}, task_id)
        
    except Exception as e:
        print(f"[错误] 转录任务异常: {e}")
        await manager.send_json({"status": "error", "message": str(e)}, task_id)
    finally:
        # 清理临时提取的音频文件
        try:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
        except Exception as e:
            print(f"[警告] 清理临时音频文件失败: {e}")
            
        # 清理上传的原视频文件，释放大量磁盘空间
        try:
            video_path_local = locals().get("video_path")
            if video_path_local and os.path.exists(video_path_local):
                os.remove(video_path_local)
                print(f"[*] 已清理原视频文件: {video_path_local}")
        except Exception as e:
            print(f"[警告] 清理视频文件失败: {e}")
        
        # 任务结束：减少并发计数。如果归零，说明系统闲下来了，启动倒计时
        active_tasks_count -= 1
        if active_tasks_count <= 0:
            active_tasks_count = 0
            idle_timer_task = asyncio.create_task(auto_unload_timer())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)