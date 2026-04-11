from src.MCPServer import *
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import multiprocessing as mp
import asyncio
import numpy as np
from core.logger import monitor
import json


with open("src/test_config.json", "r") as f:
    config_data = json.load(f)

BUFFER_SIZE = 3
FRAME_SIZE = 1024
NUM_CHANNELS = config_data["channels"]


def ring_buffer_package(name: str, buffer_size: int, frame_size: int, dtype=np.float32):
    """
    Creates a standardized SharedMemory package with a fixed system name.

    :param name: Unique system-wide name for the SHM segment (e.g., 'ch_0_buf')
    :param buffer_size: Number of frames in the ring buffer
    :param frame_size: Number of samples per frame
    :param dtype: Data type of audio samples
    :return: (package_dict, shm_object)
    """
    shm_size = np.dtype(dtype).itemsize * buffer_size * frame_size
    shm = shared_memory.SharedMemory(create=True, size=shm_size, name=name)
    package = {
        "buffer_size": buffer_size,
        "frame_size": frame_size,
        "memory_name": shm.name,
        "read_flag": mp.Value('i', 0),
        "write_flag": mp.Value('i', 0),
        "read_lock": mp.Lock(),
        "write_lock": mp.Lock(),
        "dtype": dtype
    }
    return package, shm


radio_output_packages, radio_output_shms = [], []

for i in range(NUM_CHANNELS):
    pkg, shm = ring_buffer_package(f"ch_{i}_buf", 3, 1024)
    radio_output_packages.append(pkg)
    radio_output_shms.append(shm)

main_server = MainServer(config_data, radio_output_packages, [])

@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor.log_event("HUB_BOOT", message="Initializing Hub Resources")
    loop = asyncio.get_running_loop()
    asyncio.create_task(main_server.run(loop))
    yield
    main_server.stop()
    for s in radio_output_shms:
        s.close()
        s.unlink()
    monitor.log_event("HUB_OFFLINE", message="Shared Memory released")


app = FastAPI(
    title="Mission Control Server Hub",
    lifespan=lifespan
)


@app.post("/manager/instruction", tags=["Manager Control"])
async def receive_instruction(instruction: dict):
    """
    The primary control gateway for the Mission Control Manager.
    Accepts routing and state instructions to update the summing mixer.

    Payload format: {"command": int, "data": dict}
    """
    monitor.log_event("MANAGER_CMD", event_data=instruction)
    try:
        main_server.execute_manager_command(instruction)
        return {"ok": True, "message": "Instruction executed"}
    except Exception as e:
        monitor.log_error("INSTRUCTION_FAIL", e)
        raise HTTPException(status_code=400, detail=f"Instruction failed: {str(e)}")



@app.get("/state/tablets", tags=["Status"])
async def get_active_tablets():
    """Returns a list of all tablets currently connected to the Hub."""
    tablets = []
    for socket in main_server.user_sockets:
        if socket.is_active():
            tablets.append({
                "ip_address": socket.ip_address,
                "port": socket.port,
                "name": socket.name
            })
    return {"ok": True, "tablets": tablets}


@app.post("/tablet/add/{ip_address}", tags=["Tablet Mgmt"])
def add_tablet(ip_address: str, port: int | None = None):
    """Manually registers a tablet to the Hub's communication list."""
    try:
        target_port = port or main_server.remote_communication_port
        main_server.add_user((ip_address, target_port))
        monitor.log_event("API_ADD_REQUEST", {"ip": ip_address, "port": target_port})
        return {"ok": True}
    except Exception:
        return {"ok": False}


@app.post("/tablet/kick/{ip_address}", tags=["Tablet Mgmt"])
def kick_tablet(ip_address: str, port: int | None = None):
    """Removes a tablet from the Hub and closes its audio streams."""
    try:
        target_port = port or main_server.remote_communication_port
        main_server.remove_user((ip_address, target_port))
        monitor.log_event("API_KICK_REQUEST", {"ip": ip_address}, level="WARN")
        return {"ok": True}
    except KeyError:
        return {"ok": False}


# --- Hub Service Controls ---

@app.post("/server/start", tags=["Service Control"])
async def start_hub():
    """Initializes the audio summing engine if it is not running."""
    if main_server.state() != "off":
        return {"ok": False, "error": "Server already running"}
    loop = asyncio.get_running_loop()
    asyncio.create_task(main_server.run(loop))
    monitor.log_event("HUB_START_CMD", message="Manual engine start via API")
    return {"ok": True}


@app.post("/server/stop", tags=["Service Control"])
def stop_hub():
    """Stops all audio processing and UDP listeners."""
    if main_server.state() != "on":
        return {"ok": False, "error": "Server not running"}
    main_server.stop()
    monitor.log_event("HUB_STOP_CMD", level="WARN", message="Manual engine stop via API")
    return {"ok": True}


@app.post("/server/restart", tags=["Service Control"])
async def restart_hub():
    """
    Performs a 'soft restart' of the audio engine.
    It stops the processing loops, resets the server state, and re-launches
    the background tasks without unlinking Shared Memory segments.
    """
    print("RESTART_SEQUENCE: Initiating soft restart of the Hub...")

    if main_server.state() == "on":
        main_server.stop()
        await asyncio.sleep(0.5)
    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(main_server.run(loop))

        monitor.log_event("HUB_RESTART_SUCCESS", message="Hub engine successfully rebooted")

        print("RESTART_SEQUENCE: Hub engine is back online.")
        return {"ok": True, "status": "restarted"}
    except Exception as e:
        print(f"RESTART_FAILED: {str(e)}")
        return {"ok": False, "error": str(e)}