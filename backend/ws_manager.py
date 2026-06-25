from fastapi import WebSocket
from typing import Dict, List
import asyncio

class ConnectionManager:
    def __init__(self):
        # Maps batch_id -> list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # We need a lock since background tasks and the main thread might access this concurrently
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, batch_id: str):
        await websocket.accept()
        async with self.lock:
            if batch_id not in self.active_connections:
                self.active_connections[batch_id] = []
            self.active_connections[batch_id].append(websocket)

    async def disconnect(self, websocket: WebSocket, batch_id: str):
        async with self.lock:
            if batch_id in self.active_connections:
                if websocket in self.active_connections[batch_id]:
                    self.active_connections[batch_id].remove(websocket)
                if not self.active_connections[batch_id]:
                    del self.active_connections[batch_id]

    async def broadcast_to_batch(self, batch_id: str, message: dict):
        """Sends a JSON message to all clients listening to a specific batch_id."""
        async with self.lock:
            if batch_id in self.active_connections:
                for connection in self.active_connections[batch_id]:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        print(f"WS send error: {e}")

manager = ConnectionManager()
