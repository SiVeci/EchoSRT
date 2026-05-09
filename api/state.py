import asyncio
from typing import Dict

# 任务队列
q_extract = asyncio.Queue()
q_transcribe = asyncio.Queue()
q_translate = asyncio.Queue()

# 全局任务状态字典 (用于前端轮询看板)
# key: task_id, value: {"steps": [...], "current_step": "...", "config": {...}}
global_tasks_status: Dict[str, dict] = {}

# 全局下载模型状态字典
global_downloading_models: Dict[str, dict] = {}

# 全局媒体库发现列表
# key: fingerprint, value: {"path": "...", "size": 0, "mtime": 0, "status": "new/imported"}
global_library_discoveries: Dict[str, dict] = {}