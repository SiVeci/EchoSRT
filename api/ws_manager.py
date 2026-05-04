import asyncio
from typing import Dict
from fastapi import WebSocket

class ConnectionManager:
    """
    管理 WebSocket 连接、锁和任务状态的单例类。
    """
    def __init__(self):
        # 存储活跃的 WebSocket 连接
        self.active_connections: Dict[str, WebSocket] = {}
        # 为每个任务的 WebSocket 连接提供一个锁，防止并发写入
        self.locks: Dict[str, asyncio.Lock] = {}
        # 缓存每个任务的最新状态，用于 HTTP 轮询
        self.task_states: Dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        """接受新的 WebSocket 连接并进行注册"""
        await websocket.accept()
        self.active_connections[task_id] = websocket
        self.locks[task_id] = asyncio.Lock()

    def disconnect(self, task_id: str, websocket: WebSocket = None):
        """断开并清理 WebSocket 连接"""
        if task_id in self.active_connections:
            if websocket is None or self.active_connections[task_id] == websocket:
                del self.active_connections[task_id]
                if task_id in self.locks:
                    del self.locks[task_id]

    async def send_json(self, data: dict, task_id: str):
        """向指定的客户端安全地发送 JSON 数据"""
        self.task_states[task_id] = data
        
        ws = self.active_connections.get(task_id)
        lock = self.locks.get(task_id)
        if ws and lock:
            try:
                async with lock:
                    await ws.send_json(data)
            except Exception:
                pass

manager = ConnectionManager()