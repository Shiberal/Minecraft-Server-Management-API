from prisma import Prisma
import secrets
from datetime import datetime, timedelta, timezone


#decorator definition
def prisma_connection_boilerplate(func):
    async def wrapper(*args, **kwargs):
        await args[0].prisma.connect()
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            print(e)
        finally:
            await args[0].prisma.disconnect()
    return wrapper


class UserController:
    def __init__(self):
        self.prisma = Prisma()

    @prisma_connection_boilerplate
    async def get_all(self):
        return await self.prisma.user.find_many()
   
    @prisma_connection_boilerplate
    async def new_user(self, email: str, password: str):
        return await self.prisma.user.create(data={"email": email, "password": password})
    
    
    @prisma_connection_boilerplate
    async def get_user_by_email(self, email: str):
        return await self.prisma.user.find_unique(where={"email": email})
    
    
    @prisma_connection_boilerplate
    async def get_user_by_id(self, id: int):
        return await self.prisma.user.find_unique(where={"id": id})

    
    @prisma_connection_boilerplate
    async def create_session(self, user_id: int) -> str:
        # Generate a secure random session key
        session_key = secrets.token_urlsafe(32)
        
        # Create a session that expires in 24 hours
        expires_at = datetime.utcnow() + timedelta(hours=24)
        
        # Create the session in the database
        await self.prisma.session.create(data={
            "key": session_key,
            "userId": user_id,
            "expiresAt": expires_at
        })
        
        return session_key
       
    @prisma_connection_boilerplate
    async def validate_session(self, session_key: str):
        session = await self.prisma.session.find_unique(
                where={"key": session_key},
                include={"user": True}
            ) 
        
        if not session:
            return None
                
        # Check if session is expired
        if session.expiresAt < datetime.now(timezone.utc):
            # Delete expired session
            await self.prisma.session.delete(where={"id": session.id})
            return None
                
        return session.user
    

    @prisma_connection_boilerplate
    async def delete_session(self, session_key: str):
        await self.prisma.session.delete(where={"key": session_key})
    
    @prisma_connection_boilerplate
    async def get_session(self, session_key: str):
        return await self.prisma.session.find_unique(
            where={"key": session_key},
            include={"user": True}
        )
    
    @prisma_connection_boilerplate
    async def new_session(self, user_id: int):
        return await self.create_session(user_id)


    @prisma_connection_boilerplate
    async def renew_session(self, session_key: str):
        # Get the session with user included
        session = await self.prisma.session.find_unique(
            where={"key": session_key},
            include={"user": True}
        )
        
        if session is None:
            return None
            
        # Delete the old session
        await self.prisma.session.delete(where={"key": session_key})
        
        # Create new session
        new_key = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        
        await self.prisma.session.create(data={
            "key": new_key,
            "userId": session.user.id,
            "expiresAt": expires_at
        })
        
        return new_key
