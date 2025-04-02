import importlib
import os
from typing import Union
from fastapi import FastAPI
from src.views.user_view import UserView
from src.views.server_view import ServerView


app = FastAPI()

#user management
app.include_router(UserView().router)
app.include_router(ServerView().router)





