from fastapi import APIRouter, Body, HTTPException
from ..services import library_service, config_service, workspace_service
from ..services.library_service import DEFAULT_ALLOWED_EXTENSIONS
import os

router = APIRouter()

@router.get("/library/paths")
async def get_library_paths():
    """获取当前配置的媒体库扫描路径"""
    config = await config_service.get_config()
    return config.get("library", {}).get("library_paths", [])

@router.post("/library/paths")
async def add_library_path(path: str = Body(..., embed=True)):
    """添加新的扫描路径"""
    if not os.path.exists(path) or not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="路径不存在或不是有效目录")
    
    config = await config_service.get_config()
    if "library" not in config:
        config["library"] = {
            "library_paths": [], 
            "allowed_extensions": DEFAULT_ALLOWED_EXTENSIONS, 
            "auto_scan_enabled": False
        }
    
    if path not in config["library"]["library_paths"]:
        config["library"]["library_paths"].append(path)
        await config_service.update_config(config)
    
    return {"message": "路径已添加", "paths": config["library"]["library_paths"]}

@router.delete("/library/paths")
async def delete_library_path(path: str = Body(..., embed=True)):
    """删除扫描路径"""
    config = await config_service.get_config()
    if "library" in config and path in config["library"]["library_paths"]:
        config["library"]["library_paths"].remove(path)
        await config_service.update_config(config)
    
    return {"message": "路径已删除", "paths": config.get("library", {}).get("library_paths", [])}

@router.post("/library/scan")
async def scan_library():
    """触发全量扫描，返回新发现的文件列表"""
    new_files = await library_service.scan_library()
    return {
        "new_files": new_files, 
        "total_discoveries": len(library_service.get_all_discoveries())
    }

@router.get("/library/discoveries")
async def get_discoveries():
    """获取所有已发现的文件"""
    return library_service.get_all_discoveries()

@router.post("/library/import")
async def import_from_library(payload: dict = Body(...)):
    """批量从媒体库导入文件为正式任务"""
    # payload: {"paths": ["/abs/path/1", "/abs/path/2"]}
    paths = payload.get("paths", [])
    if not paths:
        raise HTTPException(status_code=400, detail="未指定导入文件路径")
    
    imported_tasks = []
    for path in paths:
        try:
            res = await workspace_service.create_workspace_from_path(path)
            imported_tasks.append(res)
        except Exception as e:
            # 单个文件导入失败不影响整体
            print(f"[!] 导入文件 {path} 失败: {str(e)}")
        
    return {
        "message": f"成功导入 {len(imported_tasks)} 个文件", 
        "tasks": imported_tasks
    }
