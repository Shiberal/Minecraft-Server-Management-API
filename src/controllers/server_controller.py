import os
import shutil
import subprocess
import requests
from typing import Optional
from fastapi import HTTPException
from prisma import Prisma
import mcrcon
import asyncio
from src.middleware.isAuth import IsAuth
import re


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


class ServerController:
    def __init__(self):
        self.prisma = Prisma()
        


    @prisma_connection_boilerplate
    async def create_server(self, session_key: str, name: str, ip: str, port: int, start_cmd: str, stop_cmd: str, restart_cmd: str, eula: bool, modpack_url: Optional[str] = None, modpack_version: Optional[str] = None, modpack_type: Optional[str] = None , version: str = "1.21.5"):
        session = await IsAuth(session_key)()
        if not session:
            return HTTPException(status_code=401, detail="Unauthorized")
        
        
        if version:
            #create base folder for server
            os.makedirs(f"./servers/base/{version}", exist_ok=True)
            #download server jar for vanilla minecraft
            base_url = f"https://mcversions.net/download/{version}"
            print("downloading server jar for version", version)
            try:
                # First get the webpage content
                response = requests.get(base_url)
                print("webpage response status:", response.status_code)
                
                if response.status_code == 200:
                    # Extract the actual download URL from the webpage
                    download_url_match = re.search(r'href="(https://piston-data[^"]*\.jar)"', response.text)
                    if download_url_match:
                        download_url = download_url_match.group(1)
                        print("found download URL:", download_url)
                        
                        # Download the actual server jar
                        jar_response = requests.get(download_url)
                        print("jar download status:", jar_response.status_code)
                        
                        if jar_response.status_code == 200:
                            server_jar_path = f"./servers/base/{version}/server.jar"
                            print(f"writing to {server_jar_path}")
                            with open(server_jar_path, "wb") as f:
                                f.write(jar_response.content)
                            print("server jar downloaded successfully")
                            
                            # Verify file was written
                            if os.path.exists(server_jar_path):
                                file_size = os.path.getsize(server_jar_path)
                                print(f"file size: {file_size} bytes")
                            else:
                                print("file was not created")
                                return HTTPException(status_code=500, detail="Failed to write server jar file")
                        else:
                            print("jar download failed with status:", jar_response.status_code)
                            return HTTPException(status_code=500, detail="Failed to download server jar")
                    else:
                        print("could not find download URL in webpage")
                        return HTTPException(status_code=500, detail="Could not find download URL")
                else:
                    print("webpage download failed with status:", response.status_code)
                    return HTTPException(status_code=500, detail="Failed to access Minecraft website")
            except Exception as e:
                print("exception during download:", str(e))
                return HTTPException(status_code=500, detail=f"Error during download: {str(e)}")
            
        
        if modpack_url or modpack_version or modpack_type:
            return HTTPException(status_code=501, detail="Not implemented Modpack download")
        
        # Create server record in database first
        server = await self.prisma.mcserver.create(data={
            "name": name,
            "ip": ip,
            "port": port,
            "folder": name,
            "start_cmd": start_cmd,
            "stop_cmd": stop_cmd,
            "restart_cmd": restart_cmd,
            "eula": eula,
            "user_id": session.user.id,
            "rcon_port": 25575,
            "password": "minecraft"
        })
        
        #copy server files from base folder to server folder
        shutil.copytree(f"./servers/base/{version}", f"./servers/{name}", dirs_exist_ok=True )
        
        #create eula.txt
        if eula:
            with open(f"./servers/{name}/eula.txt", "w") as f:
                f.write("eula=true")
        
        #create folder
        os.makedirs(f"./servers/{name}", exist_ok=True)
        
        # Start server in a detached screen session
        screen_cmd = f"screen -dmS {name} bash -c 'cd ./servers/{name} && {start_cmd}'"
        process = subprocess.Popen(screen_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            return HTTPException(status_code=500, detail="Failed to start server")
            
        # Wait a moment for server.properties to be generated
        await asyncio.sleep(5)
                
        #replace fields in server.properties
        properties_path = f"./servers/{name}/server.properties"
        try:
            with open(properties_path, "r") as f:
                properties = f.read()
                
            # Update server properties
            properties = properties.replace("server-port=25565", f"server-port={port}")
            properties = properties.replace("server-ip=", f"server-ip={ip}")
            properties = properties.replace("enable-rcon=false", "enable-rcon=true")
            properties = properties.replace("rcon.password=", "rcon.password=minecraft")
            properties = properties.replace("rcon.port=25575", "rcon.port=25575")
            
            with open(properties_path, "w") as f:
                f.write(properties)
                
            # Restart server to apply new properties
            subprocess.run(f"screen -S {name} -X stuff 'stop\n'", shell=True)
            await asyncio.sleep(2)
            subprocess.run(f"screen -S {name} -X stuff '{start_cmd}\n'", shell=True)
            
        except Exception as e:
            print(f"Error updating server.properties: {e}")
            # Continue even if properties update fails
        
        return server
    
    @prisma_connection_boilerplate
    async def start_server(self, session_key: str, server_id: int):
        session = await IsAuth(session_key)()
        if not session:
            return HTTPException(status_code=401, detail="Unauthorized")
        
        server = await self.prisma.mcserver.find_unique(where={"id": server_id})
        if not server:
            return HTTPException(status_code=404, detail="Server not found")
        
        # Check if screen session already exists
        check_screen = subprocess.run(f"screen -ls | grep {server.name}", shell=True, capture_output=True)
        if check_screen.returncode == 0:
            return HTTPException(status_code=400, detail="Server is already running")
        
        # Create new screen session and start server
        screen_cmd = f"screen -dmS {server.name} bash -c 'cd ./servers/{server.folder} && {server.start_cmd}'"
        process = subprocess.run(screen_cmd, shell=True, capture_output=True)
        
        if process.returncode != 0:
            return HTTPException(status_code=500, detail="Failed to start server")
        
        return {
            "status": "online",
            "message": "Server started successfully"
        }
    
    @prisma_connection_boilerplate
    async def stop_server(self, session_key: str, server_id: int):
        session = await IsAuth(session_key)()
        if not session:
            return HTTPException(status_code=401, detail="Unauthorized")
            
        server = await self.prisma.mcserver.find_unique(where={"id": server_id, "user_id": session.user.id})
        if not server:
            return HTTPException(status_code=404, detail="Server not found")

        try:
            # Create RCON connection
            rcon = mcrcon.MCRcon(host=server.ip, port=int(server.rcon_port), password=server.password)
            rcon.connect()
            
            # Send stop command
            rcon.command("stop")
            
            # Close the connection
            rcon.disconnect()
            
            # Wait a moment for server to stop
            await asyncio.sleep(2)
            
            # Kill the screen session
            subprocess.run(f"screen -S {server.name} -X quit", shell=True, capture_output=True)
            
            return {
                "status": "offline",
                "message": "Server stopped successfully"
            }
            
        except Exception as e:
            return HTTPException(status_code=500, detail=f"Failed to stop server: {str(e)}")
    
    @prisma_connection_boilerplate
    async def restart_server(self, server_id: int):
        return HTTPException(status_code=501, detail="Not implemented")
    
    @prisma_connection_boilerplate
    async def list_servers(self, session_key: str):
        session = await IsAuth(session_key)()
        if not session:
            return HTTPException(status_code=401, detail="Unauthorized")
        
        servers = await self.prisma.mcserver.find_many(where={"user_id": session.user.id})
        return servers
    
    @prisma_connection_boilerplate
    async def get_server_status(self, server_id: int, session_key: str):
        session = await IsAuth(session_key)()
        if not session:
            return HTTPException(status_code=401, detail="Unauthorized")
        
        server = await self.prisma.mcserver.find_unique(where={"id": server_id, "user_id": session.user.id})
        if not server:
            return HTTPException(status_code=404, detail="Server not found")

        try:
            # Create RCON connection
            print ("server.ip",server.ip)
            print ("server.rcon_port",server.rcon_port)
            print ("server.password",server.password)
            ip = server.ip
            rcon = mcrcon.MCRcon(host=ip, port = int(server.rcon_port), password=server.password or "minecraft")  # Default password is "minecraft"
            print("created rcon connection")
            # Try to connect to the server
            rcon.connect()
            print("connected to server")
            # Send a simple command to check if server is responsive
            players = rcon.command("list")
            time = rcon.command("time query day")



            # Close the connection
            rcon.disconnect()
            
            return {
                "status": "online",
                "players": players,
                "time": time
            }
            
            
        except Exception as e:
            return {
                "status": "offline",
                "error": str(e)
            }
        
    @prisma_connection_boilerplate
    async def restart_server(self, session_key: str, server_id: int):
        session = await IsAuth(session_key)()
        if not session:
            return HTTPException(status_code=401, detail="Unauthorized")
        
        server = await self.prisma.mcserver.find_unique(where={"id": server_id, "user_id": session.user.id})
        if not server:
            return HTTPException(status_code=404, detail="Server not found")
        
        try:
            # Create RCON connection
            rcon = mcrcon.MCRcon(host=server.ip, port=int(server.rcon_port), password=server.password)
            rcon.connect()
            
            # Send restart command
            rcon.command("stop")
            
            # Close the connection
            rcon.disconnect()
            
            #try to connect to the server again
            while rcon.connect():
                await asyncio.sleep(1)
                print("connected to server")
            print("killed connection to server")
            
            # Kill the screen session
            subprocess.run(f"screen -S {server.name} -X quit", shell=True, capture_output=True)
            
            # Start server in a new screen session
            subprocess.run(f"screen -dmS {server.name} bash -c 'cd ./servers/{server.folder} && {server.start_cmd}'", shell=True, capture_output=True)
            
            return {
                "status": "restarting",
                "message": "Server restarted successfully"
            }
            
        except Exception as e:
            return HTTPException(status_code=500, detail=f"Failed to restart server: {str(e)}")
        
        return HTTPException(status_code=501, detail="Not implemented") 
    
    @prisma_connection_boilerplate
    async def delete_server(self, session_key: str, server_id: int):
        session = await IsAuth(session_key)()


        
        if not session:
            return HTTPException(status_code=401, detail="Unauthorized")
        
        server = await self.prisma.mcserver.find_unique(where={"id": server_id, "user_id": session.user.id})
       
        #make sure server is not running 
        check_screen = subprocess.run(f"screen -ls | grep {server.name}", shell=True, capture_output=True)
        if check_screen.returncode == 0:
            return HTTPException(status_code=400, detail="Server is running stop it first")
        
        if not server:
            return HTTPException(status_code=404, detail="Server not found")
        
        #delete server folder
        shutil.rmtree(f"./servers/{server.name}")
        
        #delete server from database
        await self.prisma.mcserver.delete(where={"id": server_id})
        
        
        return {
            "status": "deleted",
            "message": "Server deleted successfully"
        }