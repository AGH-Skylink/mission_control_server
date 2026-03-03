from src.MCPServer import *
from fastapi import FastAPI
from contextlib import asynccontextmanager

BUFFER_SIZE = 3
FRAME_SIZE = 1024


def ring_buffer_package(buffer_size: int, frame_size: int, dtype=np.float32):
    shm_size = np.dtype(dtype).itemsize * buffer_size * frame_size
    shm = shared_memory.SharedMemory(create=True, size=shm_size)
    package = {"buffer_size": buffer_size,
               "frame_size": frame_size,
               "memory_name": shm.name,
               "read_flag": mp.Value('i', 0),
               "read_lock": mp.Lock(),
               "write_flag": mp.Value('i', 0),
               "write_lock": mp.Lock(),
               "dtype": dtype}
    return package, shm


uplink_buffers_packages, uplink_buffers_shm = [], []
for i in range(2):
    up_package, up_shm = ring_buffer_package(BUFFER_SIZE, FRAME_SIZE, np.float32)
    uplink_buffers_packages.append(up_package)
    uplink_buffers_shm.append(up_shm)

downlink_buffers_packages, downlink_buffers_shm = [], []
for i in range(1):
    down_package, down_shm = ring_buffer_package(BUFFER_SIZE, FRAME_SIZE, np.float32)
    downlink_buffers_packages.append(down_package)
    downlink_buffers_shm.append(down_shm)

main_server = MainServer("src/test_config.json", downlink_buffers_packages, uplink_buffers_packages)


@asynccontextmanager
async def lifespan(fast_api_app: FastAPI):
    loop = asyncio.get_running_loop()
    asyncio.create_task(main_server.run(loop))
    yield
    main_server.stop()
    for j in range(2):
        uplink_buffers_shm[j].close()
        uplink_buffers_shm[j].unlink()
    for j in range(1):
        downlink_buffers_shm[j].close()
        downlink_buffers_shm[j].unlink()


app = FastAPI(title="Mission Control Server API", version="0.1.0", lifespan=lifespan)


# TODO: add a few subcategories, like config, users, etc.
@app.get("/state/tablets")
async def get_users():
    try:
        tablets = []
        for socket in main_server.user_sockets:
            if socket.is_active():
                tablets.append({"ip_address": socket.ip_address, "port": socket.port, "name": socket.name})
            await asyncio.sleep(0)
        return {
            "ok": True,
            "tablets": tablets
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/tablet/add/{ip_address}")
def add_user(ip_address: str, port: int | None = None) -> dict:
    try:
        if port is None:
            main_server.add_user((ip_address, main_server.remote_communication_port))
        else:
            main_server.add_user((ip_address, port))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


@app.post("/tablet/kick/{ip_address}")
def kick_user(ip_address: str, port: int | None = None) -> dict:
    try:
        if port is None:
            main_server.remove_user((ip_address, main_server.remote_communication_port))
        else:
            main_server.remove_user((ip_address, port))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
    try:
        if main_server.state() != "off":
            return {"ok": False, "error": "Server is already running"}
        loop = asyncio.get_running_loop()
        asyncio.create_task(main_server.run(loop))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/stop")
def stop_server():
    try:
        if main_server.state() != "on":
            return {"ok": False, "error": "Server is already stopped"}
        main_server.stop()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/restart")
async def restart_server():
    try:
        if main_server.state() != "on":
            return {"ok": False, "error": "Server is already stopped"}
        main_server.stop()
        loop = asyncio.get_running_loop()
        asyncio.create_task(main_server.run(loop))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
