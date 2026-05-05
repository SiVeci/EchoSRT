import asyncio
from typing import Dict, List
from fastapi import WebSocket

class ConnectionManager:
    """
    管理 WebSocket 连接、锁和任务状态的单例类。
    """
    def __init__(self):
        # 存储活跃的 WebSocket 连接（一对多广播）
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # 为每个任务的 WebSocket 连接提供一个锁，防止并发写入
        self.locks: Dict[str, asyncio.Lock] = {}
        # 缓存每个任务的最新状态，用于 HTTP 轮询
        self.task_states: Dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        """接受新的 WebSocket 连接并进行注册"""
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
            self.locks[task_id] = asyncio.Lock()
        self.active_connections[task_id].append(websocket)

    def disconnect(self, task_id: str, websocket: WebSocket = None):
        """断开并清理 WebSocket 连接"""
        if task_id in self.active_connections:
            if websocket is None:
                del self.active_connections[task_id]
                self.locks.pop(task_id, None)
            else:
                if websocket in self.active_connections[task_id]:
                    self.active_connections[task_id].remove(websocket)
                if not self.active_connections[task_id]:
                    del self.active_connections[task_id]
                    self.locks.pop(task_id, None)

    async def send_json(self, data: dict, task_id: str):
        """向指定的客户端安全地进行一对多广播 JSON 数据"""
        self.task_states[task_id] = data
        
        ws_list = self.active_connections.get(task_id, [])
        lock = self.locks.get(task_id)
        if ws_list and lock:
            try:
                async with lock:
                    for ws in ws_list[:]:  # 遍历拷贝，防止中途断开改变列表
                        try:
                            await ws.send_json(data)
                        except Exception:
                            # 发送失败则认为连接已断开，直接清理
                            if ws in self.active_connections.get(task_id, []):
                                self.active_connections[task_id].remove(ws)
            except Exception:
                pass

manager = ConnectionManager()