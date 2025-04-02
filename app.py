import importlib
import os
from typing import Union
from fastapi import FastAPI
from src.views.user_view import UserView
from src.views.server_view import ServerView
from dotenv import load_dotenv

load_dotenv()

if os.getenv("MODRINTH_API_SECRET") is None:
    print("MODRINTH_API_SECRET is not set, to use modrinth you need to set the MODRINTH_API_SECRET environment variable")
if os.getenv("CLIENT_ID") is None:
    print("CLIENT_ID is not set, to use modrinth you need to set the CLIENT_ID environment variable")

app = FastAPI()


#user management
app.include_router(UserView().router)
app.include_router(ServerView().router)





