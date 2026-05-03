import asyncio
from typing import Dict

# 任务队列
q_extract = asyncio.Queue()
q_transcribe = asyncio.Queue()
q_translate = asyncio.Queue()

# 全局任务状态字典 (用于前端轮询看板)
# key: task_id, value: {"steps": [...], "current_step": "...", "config": {...}}
global_tasks_status: Dict[str, dict] = {}