from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from src.controllers.server_controller import ServerController

class ServerCreateSchema(BaseModel):
    name: str 
    ip: str = "127.0.0.1"
    port: int = 25565
    start_cmd: str = "java -jar server.jar"
    stop_cmd: str = "stop"
    restart_cmd: str = "restart"
    eula: bool = True
    modpack_url: Optional[str] = None
    modpack_version: Optional[str] = None
    modpack_type: Optional[str] = None
    version: str = "1.21.5"
class ServerView:
    def __init__(self):
        self.router = APIRouter(prefix="/server")
        self.router.post("/create")(self.create_server)
        self.router.post("/start")(self.start_server)
        self.router.post("/stop")(self.stop_server)
        self.router.post("/restart")(self.restart_server)
        self.router.post("/delete")(self.delete_server)
        self.router.post("/status")(self.get_server_status)
        self.router.post("/list")(self.list_servers)
        self.server_controller = ServerController()


        
        
    async def create_server(self, session_key: str, data: dict = Depends(ServerCreateSchema)):

        return await self.server_controller.create_server(session_key, data.name, data.ip, data.port, data.start_cmd, data.stop_cmd, data.restart_cmd, data.eula, data.modpack_url, data.modpack_version, data.modpack_type, data.version)

    async def start_server(self, session_key: str, server_id: int):
        return await self.server_controller.start_server(session_key, server_id)

    async def stop_server(self, session_key: str, server_id: int):
        return await self.server_controller.stop_server(session_key, server_id)

    async def restart_server(self, session_key: str, server_id: int):
        return await self.server_controller.restart_server(session_key, server_id)

    async def delete_server(self, session_key: str, server_id: int):
        pass
    
    
    
    async def get_server_status(self, session_key: str, server_id: int):
        return await self.server_controller.get_server_status(server_id, session_key)

    async def list_servers(self, session_key: str):
        return await self.server_controller.list_servers(session_key)

    