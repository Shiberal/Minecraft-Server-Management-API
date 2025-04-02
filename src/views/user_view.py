from fastapi import FastAPI, Request
from prisma import Prisma
from fastapi import APIRouter

from src.controllers.user_controller import UserController


class UserView:

    def __init__(self):
        self.router = APIRouter(prefix="/auth")
        self.router.post("/login")(self.login)
        self.router.post("/register")(self.register)
        self.router.post("/renew_session")(self.renew_session)
        self.controller = UserController()
    
    async def login(self, email: str, password: str):
        try:
            user = await self.controller.get_user_by_email(email)
            if user is None:
                return {"message": "User not found"}
            if user.password != password:
                return {"message": "Invalid password"}

            # Create a session for the user
            session_key = await self.controller.create_session(user.id)
            
            return {
                "message": "Login successful",
                "session_key": session_key,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name
                }
            }

        except Exception as e:
            return {"message": "Login failed", "error": str(e)}
    
    async def register(self, email: str, password: str):
        try:
            user = await self.controller.new_user(email, password)
            return {"message": "User created successfully", "user": user}
        except Exception as e:
            return {"message": "User creation failed", "error": str(e)}
    
    async def renew_session(self, session_key: str):
        try:
            key = await self.controller.renew_session(session_key)
            if key is None:
                return {"message": "Session renewal failed", "error": "Invalid or expired session"}
           
            return {"message": "Session renewed successfully", "session_key": key}
        except Exception as e:
            return {"message": "Session renewal failed", "error": str(e)}

