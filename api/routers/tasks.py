from fastapi import APIRouter, UploadFile, File, Form, Body, HTTPException
from fastapi.responses import FileResponse
from ..services import workspace_service, dispatcher_service

router = APIRouter()

@router.post("/upload/{asset_type}")
async def upload_asset(asset_type: str, file: UploadFile = File(...), task_id: str = Form(None)):
    return await workspace_service.save_asset(file, asset_type, task_id)

@router.post("/task/execute")
async def execute_task(payload: dict = Body(...)):
    return await dispatcher_service.dispatch_task(payload)

@router.post("/task/{task_id}/retry")
async def retry_task(task_id: str):
    return await dispatcher_service.retry_task(task_id)

@router.get("/download/{task_id}")
async def download_srt(task_id: str, type: str = "original"):
    target_file, out_name = await workspace_service.get_download_file_path(task_id, type)
    return FileResponse(target_file, media_type="text/plain", filename=out_name)

@router.get("/task/{task_id}/assets")
def get_task_assets(task_id: str):
    return workspace_service.get_single_task(task_id)

@router.get("/tasks")
def list_tasks():
    return workspace_service.get_all_tasks()

@router.delete("/task/{task_id}")
async def delete_task(task_id: str):
    return await workspace_service.delete_task_workspace(task_id)

@router.delete("/task/{task_id}/asset/{asset_type}")
async def delete_task_asset(task_id: str, asset_type: str):
    return await workspace_service.delete_single_asset(task_id, asset_type)

@router.post("/tasks/reorder")
def reorder_tasks(task_ids: list[str] = Body(...)):
    return workspace_service.reorder_tasks(task_ids)

@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    await dispatcher_service.cancel_task(task_id)
    return {"message": "任务已发送中断信号"}

@router.post("/tasks/cancel_all")
async def cancel_all_tasks():
    await dispatcher_service.cancel_all_tasks()
    return {"message": "所有任务已发送中断信号"}
