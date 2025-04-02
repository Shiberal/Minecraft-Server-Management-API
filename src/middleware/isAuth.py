from fastapi import HTTPException, Request
from src.controllers.user_controller import UserController

class IsAuth:
    def __init__(self, session_key: str):
        self.session_key = session_key
        self.user_controller = UserController()
        
    async def __call__(self):
        session = await self.user_controller.get_session(self.session_key)
        
        if session is None:
            return None
        
        return session
