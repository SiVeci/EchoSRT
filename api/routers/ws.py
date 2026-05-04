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
    return global_tasks_status