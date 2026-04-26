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
        await manager.send_json({"status": "processing", "step": "extract_audio", "message": "正在提取音频..."}, task_id)
        await loop.run_in_executor(None, extract_audio, video_path, temp_audio_path)
        
        # 2. 加载模型与识别阶段
        await manager.send_json({"status": "processing", "step": "transcribing", "message": "开始语音识别..."}, task_id)
        
        model_settings = config_payload.get("model_settings", {})
        transcribe_settings = config_payload.get("transcribe_settings", {})
        vad_settings = config_payload.get("vad_settings", {})

        segments = await loop.run_in_executor(
            None,
            transcribe_audio,
            temp_audio_path,
            model_settings,
            transcribe_settings,
            vad_settings
        )

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