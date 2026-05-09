import os
import hashlib
import json
import platform
from pathlib import Path
from typing import List, Dict, Set
from .config_service import get_config
from ..state import global_library_discoveries

# 默认支持的媒体格式列表
DEFAULT_ALLOWED_EXTENSIONS = [
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".ts", ".m2ts", ".rmvb", ".vob", ".asf",
    ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma", ".opus"
]

def generate_fingerprint(file_path: Path) -> str:
    """生成文件指纹：路径(针对 OS 优化) + 文件大小 + 修改时间"""
    try:
        stat = file_path.stat()
        # 路径标准化：Windows 强制小写防止指纹偏差，Linux/macOS 原样保留绝对路径
        norm_path = str(file_path.absolute())
        if platform.system() == "Windows":
            norm_path = norm_path.lower()
            
        raw_str = f"{norm_path}|{stat.st_size}|{stat.st_mtime}"
        return hashlib.md5(raw_str.encode()).hexdigest()
    except Exception:
        return ""

def get_active_fingerprints() -> Set[str]:
    """实时扫描工作区，获取所有已导入任务的指纹"""
    active_fps = set()
    workspace_dir = os.path.join(os.getcwd(), "workspace")
    if not os.path.exists(workspace_dir):
        return active_fps
        
    try:
        for task_id in os.listdir(workspace_dir):
            task_dir = os.path.join(workspace_dir, task_id)
            if not os.path.isdir(task_dir):
                continue
            meta_path = os.path.join(task_dir, "meta.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    fp = meta.get("fingerprint")
                    if fp:
                        active_fps.add(fp)
    except Exception as e:
        print(f"[!] 扫描工作区指纹失败: {str(e)}")
    return active_fps

async def scan_library() -> List[dict]:
    """执行媒体库全量扫描 (优化版：单次遍历 + 磁盘状态自愈)"""
    config = await get_config()
    library_config = config.get("library", {})
    paths = library_config.get("library_paths", [])
    # 兜底：如果配置中的扩展名列表为空，强制使用系统默认列表
    extensions = library_config.get("allowed_extensions")
    if not extensions:
        extensions = DEFAULT_ALLOWED_EXTENSIONS
    
    # 获取磁盘上真实存在的已导入指纹
    imported_fps = get_active_fingerprints()
    
    # 转为小写集合以便 O(1) 匹配
    ext_set = {ext.lower() for ext in extensions}
    new_discoveries = []
    
    # 清空内存中的临时旧缓存，以本次扫描结果为准
    global_library_discoveries.clear()
    
    for path_str in paths:
        root = Path(path_str)
        if not root.exists() or not root.is_dir():
            continue
            
        try:
            for file_path in root.rglob("*"):
                if not file_path.is_file():
                    continue
                
                if file_path.suffix.lower() not in ext_set:
                    continue
                    
                fp = generate_fingerprint(file_path)
                if not fp:
                    continue
                
                # 状态判定：如果磁盘工作区没有这个指纹，就是新视频
                status = "imported" if fp in imported_fps else "new"
                
                discovery = {
                    "fingerprint": fp,
                    "path": str(file_path.absolute()),
                    "filename": file_path.name,
                    "size": file_path.stat().st_size,
                    "mtime": file_path.stat().st_mtime,
                    "status": status
                }
                
                global_library_discoveries[fp] = discovery
                if status == "new":
                    new_discoveries.append(discovery)
                    
        except Exception as e:
            print(f"[!] 扫描目录 {path_str} 时出错: {str(e)}")
                        
    return new_discoveries

def get_all_discoveries() -> List[dict]:
    """获取所有已发现的文件列表"""
    return list(global_library_discoveries.values())

def clear_discoveries():
    """清除发现列表"""
    global_library_discoveries.clear()
