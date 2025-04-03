import json
import os
import shutil
import subprocess
import zipfile
import requests
from typing import Optional
from fastapi import HTTPException
from prisma import Prisma
import mcrcon
import asyncio
from src.middleware.isAuth import IsAuth
import re


useragent = "ServerManager/0.1"
modpack_base_folder = "./servers/base/modpacks"

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
    async def create_server(self, session_key: str, name: str, ip: str, port: int, start_cmd: str, stop_cmd: str, restart_cmd: str, eula: bool, modpack_url: Optional[str] = None, modpack_version: Optional[str] = None, modpack_type: Optional[str] = None , version: str = "1.21.5", port_rcon: int = 25575):
        try:
            session = await IsAuth(session_key)()
            if not session:
                return HTTPException(status_code=401, detail="Unauthorized")
            
            if modpack_url and modpack_version and modpack_type:
                
                print("modpack_url", modpack_url)
                
                #get string after last / in modpack_url
                modpackName = modpack_url.split("/")[-1]
                project_base_url = f"https://api.modrinth.com/v2/project/{modpackName}/version"

                #get all modpack_versions of the project
                modpack_versions = requests.get(project_base_url, headers={"User-Agent": useragent})
                #print to file
                modpack_versions = list(modpack_versions.json())
                modpack_versions = [version for version in modpack_versions if version["version_number"] == modpack_version]
                mpack_version_url = modpack_versions[0]["files"][0]["url"]

                #download the version
                mrpack_file = requests.get(mpack_version_url, headers={"User-Agent": useragent})
                #create folders 
                os.makedirs(f"{modpack_base_folder}/{modpackName}/{modpack_version}", exist_ok=True)
                
                with open(f"{modpack_base_folder}/{modpackName}/{modpack_version}/pack.mrpack", "wb") as f:
                    f.write(mrpack_file.content)
                    
                #make temp folder
                os.makedirs(f"{modpack_base_folder}/{modpackName}/{modpack_version}/temp", exist_ok=True)
            
                #unzip the mrpack file
                with zipfile.ZipFile(f"{modpack_base_folder}/{modpackName}/{modpack_version}/pack.mrpack", "r") as zip_ref:
                    zip_ref.extractall(f"{modpack_base_folder}/{modpackName}/{modpack_version}/temp")
                
                #read the modrinth.index.json file
                with open(f"{modpack_base_folder}/{modpackName}/{modpack_version}/temp/modrinth.index.json", "r") as f:
                    modrinth_index = json.load(f)
                    
                minecraft_version = modrinth_index["dependencies"]["minecraft"]
                forge_version = modrinth_index["dependencies"]["forge"]
                mods = modrinth_index["files"]
                print ("minecraft_version", minecraft_version)
                print ("forge_version", forge_version)
                
                #override minecraft version
                version = minecraft_version
                
                #download forge
                forge_url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{version}-{forge_version}/forge-{version}-{forge_version}-installer.jar"
                forge_file = requests.get(forge_url, headers={"User-Agent": useragent})
                with open(f"{modpack_base_folder}/{modpackName}/{modpack_version}/temp/forge.jar", "wb") as f:
                    f.write(forge_file.content)
                

                #create path for mods
                os.makedirs(f"{modpack_base_folder}/{modpackName}/{modpack_version}/temp/stuff", exist_ok=True)
                
                for mod in mods:
                    
                    mod_url = mod["downloads"][0]
                    path = mod["path"]
                    
                    print ("mod_url", mod_url)
                    print ("path", path)
                    
                    #download and put in temp/ + path
                    #check if file already exits
                    if os.path.exists(f"{modpack_base_folder}/{modpackName}/{modpack_version}/temp/stuff/{path}"):
                        continue
                    
                    #check if path contains folders if so create them
                    mod_dir = os.path.dirname(f"{modpack_base_folder}/{modpackName}/{modpack_version}/temp/stuff/{path}")
                    if mod_dir:
                        os.makedirs(mod_dir, exist_ok=True)
                    
                    with open(f"{modpack_base_folder}/{modpackName}/{modpack_version}/temp/stuff/{path}", "wb") as f:
                        f.write(requests.get(mod_url, headers={"User-Agent": useragent}).content)

                    
                #copy mods folder from stuff to server folder ./servers/{name}
                shutil.copytree(f"{modpack_base_folder}/{modpackName}/{modpack_version}/temp/stuff/mods", f"./servers/{name}/mods")
                #copy forge.jar to server folder
                shutil.copy(f"{modpack_base_folder}/{modpackName}/{modpack_version}/temp/forge.jar", f"./servers/{name}/forge.jar")
                #copy overrides to server folder
                shutil.copytree(f"{modpack_base_folder}/{modpackName}/{modpack_version}/temp/overrides", f"./servers/{name}/", dirs_exist_ok=True )
                
                
                
                # install forge  
                try:
                    # Run forge installer with timeout
                    result = subprocess.run(
                        f"cd ./servers/{name} && java -jar forge.jar --installServer",
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 minute timeout
                    )
                    
                    # Check if installation was successful
                    if result.returncode != 0:
                        print(f"Forge installation failed: {result.stderr}")
                        return HTTPException(
                            status_code=500,
                            detail=f"Failed to install Forge: {result.stderr}"
                        )
                    
                    # Verify forge installation
                    forge_server_jar = f"./servers/{name}/libraries/net/minecraftforge/forge/{version}-{forge_version}/forge-{version}-{forge_version}-server.jar"
                    if not os.path.exists(forge_server_jar):
                        return HTTPException(
                            status_code=500,
                            detail="Forge installation completed but server jar not found"
                        )
                    
                    print("Forge installed successfully")
                    
                except subprocess.TimeoutExpired:
                    return HTTPException(
                        status_code=500,
                        detail="Forge installation timed out after 5 minutes"
                    )
                except Exception as e:
                    return HTTPException(
                        status_code=500,
                        detail=f"Error during Forge installation: {str(e)}"
                    )
            
            if version and not modpack_url and not modpack_version and not modpack_type:
                #create base folder for server
                os.makedirs(f"./servers/base/{version}", exist_ok=True)
                #download server jar for vanilla minecraft
                base_url = f"https://mcmodpack_versions.net/download/{version}"
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
                
                #copy server files from base folder to server folder
                shutil.copytree(f"./servers/base/{version}", f"./servers/{name}", dirs_exist_ok=True )
            
            
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
                "rcon_port": port_rcon,
                "password": "minecraft"
            })
            
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
            
            # Create default server.properties if it doesn't exist
            if not os.path.exists(properties_path):
                default_properties = """#Minecraft server properties
#Generated by ServerManager
server-port=25565
server-ip=
enable-rcon=false
rcon.password=
rcon.port=25575
gamemode=survival
difficulty=normal
pvp=true
max-players=20
online-mode=true
allow-flight=false
white-list=false
spawn-protection=16
view-distance=10
simulation-distance=10
spawn-monsters=true
spawn-animals=true
generate-structures=true
max-world-size=29999984
motd=A Minecraft Server
hardcore=false
enable-command-block=false
max-build-height=256
spawn-npcs=true
allow-nether=true
enforce-whitelist=false
spawn-protection=16
resource-pack=
resource-pack-sha1=
spawn-point=
level-name=world
level-seed=
level-type=default
enable-query=false
query.port=25565
prevent-proxy-connections=false
use-native-transport=true
enable-jmx-monitoring=false
enable-status=true
broadcast-rcon-to-ops=true
"""
                with open(properties_path, "w") as f:
                    f.write(default_properties)
            
            try:
                with open(properties_path, "r") as f:
                    properties = f.read()
                    
                # Update server properties
                properties = properties.replace("server-port=25565", f"server-port={port}")
                properties = properties.replace("server-ip=", f"server-ip={ip}")
                properties = properties.replace("enable-rcon=false", "enable-rcon=true")
                properties = properties.replace("rcon.password=", "rcon.password=minecraft")
                properties = properties.replace("rcon.port=25575", f"rcon.port={port_rcon}")
                properties = properties.replace("query.port=25565", f"query.port={port}")
                
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
        except Exception as e:
            #delete server folder 
            shutil.rmtree(f"./servers/{name}")
            return HTTPException(status_code=500, detail=f"Error during server creation: {str(e)}")
            
    
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