from src.MCPServer import *
from fastapi import FastAPI
from contextlib import asynccontextmanager

buffer_size = 3
frame_size = 1024

up_shm_1 = shared_memory.SharedMemory(create=True, size=4*buffer_size*frame_size, name='up_shm_1')
up_shm_2 = shared_memory.SharedMemory(create=True, size=4*buffer_size*frame_size, name='up_shm_2')
down_shm_1 = shared_memory.SharedMemory(create=True, size=4*buffer_size*frame_size, name='down_shm_1')

lock_1r = mp.Lock()
lock_1w = mp.Lock()
lock_2r = mp.Lock()
lock_2w = mp.Lock()
lock_3r = mp.Lock()
lock_3w = mp.Lock()

read_flag_1 = mp.Value('i', 0)
write_flag_1 = mp.Value('i', 0)
read_flag_2 = mp.Value('i', 0)
write_flag_2 = mp.Value('i', 0)
read_flag_3 = mp.Value('i', 0)
write_flag_3 = mp.Value('i', 0)


uplink_buffers_packages = [{"buffer_size": buffer_size,
                            "frame_size": frame_size,
                            "memory_name": "up_shm_1",
                            "read_flag": read_flag_1,
                            "read_lock": lock_1r,
                            "write_flag": write_flag_1,
                            "write_lock": lock_1w},
                           {"buffer_size": buffer_size,
                            "frame_size": frame_size,
                            "memory_name": "up_shm_2",
                            "read_flag": read_flag_2,
                            "read_lock": lock_2r,
                            "write_flag": write_flag_2,
                            "write_lock": lock_2w}]

downlink_buffers_packages = [{"buffer_size": buffer_size,
                              "frame_size": frame_size,
                              "memory_name": "down_shm_1",
                              "read_flag": read_flag_3,
                              "read_lock": lock_3r,
                              "write_flag": write_flag_3,
                              "write_lock": lock_3w}]

main_server = MainServer("src/test_config.json", downlink_buffers_packages, uplink_buffers_packages)


@asynccontextmanager
async def lifespan(fast_api_app: FastAPI):
    loop = asyncio.get_running_loop()
    asyncio.create_task(main_server.run(loop))
    yield
    main_server.stop()
    up_shm_1.close()
    up_shm_2.close()
    down_shm_1.close()
    up_shm_1.unlink()
    up_shm_2.unlink()
    down_shm_1.unlink()


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


"""@app.post("/tablet/priority/{ip_address}/{priority}")
def change_priority(ip_address: str, priority: int) -> dict:
    try:
        if not isinstance(priority, int) or priority < 0 or priority > 2:
            raise ValueError(f"Priority must be between 0 and 2, not: {priority}")
        main_server.change_priority((ip_address, main_server.remote_communication_port), priority)
    except KeyError:
        return {"ok": False}
    except ValueError:
        return {"ok": False}
    return {"ok": True}"""


@app.post("/start")
async def start_server():
    if main_server.state() != "off":
        return {"ok": False}
    loop = asyncio.get_running_loop()
    asyncio.create_task(main_server.run(loop))
    return {"ok": True}


@app.post("/stop")
def stop_server():
    if main_server.state() != "on":
        return {"ok": False}
    main_server.stop()
    return {"ok": True}


@app.post("/restart")
async def restart_server():
    if main_server.state() != "on":
        return {"ok": False}
    main_server.stop()
    loop = asyncio.get_running_loop()
    asyncio.create_task(main_server.run(loop))
    return {"ok": True}
