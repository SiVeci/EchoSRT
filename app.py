import os
import json
import asyncio
import logging
import shutil
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.routers import config, tasks, ws, library
from api.services import config_service
from api.workers import worker_extract_loop, worker_transcribe_loop, worker_translate_loop

_worker_tasks = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 针对本地直接运行 app.py 的用户：在启动前自动生成配置文件
    if not os.path.exists("config/config.json"):
        if os.path.exists("config/config.example.json"):
            os.makedirs("config", exist_ok=True)
            shutil.copy("config/config.example.json", "config/config.json")
            print("[*] 首次运行，已自动生成 config/config.json 默认配置文件。")
            
    # 应用启动时，尝试读取配置并设置全局代理
    try:
        if os.path.exists("config/config.json"):
            with open("config/config.json", "r", encoding="utf-8") as f:
                config_service.set_global_proxy(json.load(f).get("system_settings", {}))
    except Exception as e:
        print(f"[警告] 启动时设置全局代理失败: {e}")
        
    # 启动后台常驻的 Worker 任务车间
    t1 = asyncio.create_task(worker_extract_loop())
    t2 = asyncio.create_task(worker_transcribe_loop())
    t3 = asyncio.create_task(worker_translate_loop())
    _worker_tasks.update([t1, t2, t3])
    yield
    _worker_tasks.clear()

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/api/pipeline/status") == -1

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

# --- FastAPI App 初始化 ---
app = FastAPI(title="EchoSRT Web API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 挂载 API 路由 ---
app.include_router(config.router, prefix="/api", tags=["Config & System"])
app.include_router(tasks.router, prefix="/api", tags=["Tasks & Assets"])
app.include_router(library.router, prefix="/api", tags=["Media Library"])
app.include_router(ws.router, tags=["Realtime & Status"])

# --- 挂载静态文件与工作区 ---
WORKSPACE_DIR = os.path.abspath(os.path.join(os.getcwd(), "workspace"))
os.makedirs(WORKSPACE_DIR, exist_ok=True)
app.mount("/", StaticFiles(directory=os.path.join(os.getcwd(), "frontend"), html=True), name="frontend")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn", force=True)
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False, log_level="warning")
