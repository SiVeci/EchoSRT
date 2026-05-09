from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..ws_manager import manager
from ..state import global_tasks_status

router = APIRouter()

@router.websocket("/ws/progress/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await manager.connect(websocket, task_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(task_id, websocket)

@router.get("/api/task/{task_id}/status")
async def get_task_status(task_id: str):
    return manager.task_states.get(task_id, {"status": "unknown"})

@router.get("/api/pipeline/status")
async def get_pipeline_status():
    # 增量优化：只返回当前正在运行或待命的任务，过滤掉已完成和报错的陈旧状态
    # 这能极大减小前端轮询的 Payload 体积，防止内存泄漏和网络阻塞
    active_tasks = {
        tid: status for tid, status in global_tasks_status.items() 
        if status.get("current_step") not in ["completed", "error"]
    }
    return active_tasks