from src.MCPServer import *
from fastapi import FastAPI
import json

main_server = MainServer("src/test_config.json")
app = FastAPI(title="Mission Control Server API", version="0.1.0")

@app.on_event("startup")
async def startup():
    loop = asyncio.get_running_loop()
    asyncio.create_task(main_server.run(loop))

# TODO: add a few subcategories, like config, users, etc.
@app.get("/state")
def get_state():
    pass

@app.post("/tablet/add/{ip_address}")
def add_user(ip_address: str) -> dict:
    try:
        main_server.add_user((ip_address, main_server.remote_communication_port))
    except OverflowError:
        return {"result" : False}
    return {"result" : True}

@app.post("/tablet/kick/{ip_address}")
def kick_user(ip_address: str):
    try:
        main_server.remove_user((ip_address, main_server.remote_communication_port))
    except KeyError:
        return {"result": False}
    return {"result": True}

@app.post("/tablet/routing")
def change_routing_status():
    pass

@app.post("/start")
def start_server():
    pass

@app.post("/stop")
def stop_server():
    pass

@app.post("/restart")
def restart_server():
    pass