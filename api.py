from src.MCPServer import *
from fastapi import FastAPI
from contextlib import asynccontextmanager

main_server = MainServer("src/test_config.json")


@asynccontextmanager
async def lifespan(fast_api_app: FastAPI):
    loop = asyncio.get_running_loop()
    asyncio.create_task(main_server.run(loop))
    yield
    main_server.stop()


app = FastAPI(title="Mission Control Server API", version="0.1.0", lifespan=lifespan)


# TODO: add a few subcategories, like config, users, etc.
@app.get("/state/tablets")
async def get_users():
    tablets = []
    for socket in main_server.user_sockets:
        if socket.is_active():
            tablets.append({"ip_address": socket.ip_address, "port": socket.port, "name": socket.name,
                            "priority": socket.priority})
        await asyncio.sleep(0)
    return {
        "ok": True,
        "tablets": tablets
    }


@app.post("/tablet/add/{ip_address}")
def add_user(ip_address: str) -> dict:
    try:
        main_server.add_user((ip_address, main_server.remote_communication_port))
    except OverflowError:
        return {"ok": False}
    return {"ok": True}


@app.post("/tablet/kick/{ip_address}")
def kick_user(ip_address: str) -> dict:
    try:
        main_server.remove_user((ip_address, main_server.remote_communication_port))
    except KeyError:
        return {"ok": False}
    return {"ok": True}


@app.post("/tablet/priority/{ip_address}/{priority}")
def change_priority(ip_address: str, priority: int) -> dict:
    try:
        if not isinstance(priority, int) or priority < 0 or priority > 2:
            raise ValueError(f"Priority must be between 0 and 2, not: {priority}")
        main_server.change_priority((ip_address, main_server.remote_communication_port), priority)
    except KeyError:
        return {"ok": False}
    except ValueError:
        return {"ok": False}
    return {"ok": True}


@app.post("/start")
async def start_server():
    loop = asyncio.get_running_loop()
    asyncio.create_task(main_server.run(loop))


@app.post("/stop")
def stop_server():
    main_server.stop()


@app.post("/restart")
async def restart_server():
    main_server.stop()
    loop = asyncio.get_running_loop()
    asyncio.create_task(main_server.run(loop))