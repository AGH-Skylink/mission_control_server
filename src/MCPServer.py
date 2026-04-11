import asyncio
import json
import numpy as np
import multiprocessing as mp
from multiprocessing import shared_memory
from core.logger import monitor

class RingBuffer:
    def __init__(self, shm_package: dict):
        self.buffer_size = shm_package["buffer_size"]
        self.frame_size = shm_package["frame_size"]
        self.dtype = shm_package["dtype"]

        if shm_package["memory_name"]:
            self.shm_memory = shared_memory.SharedMemory(name=shm_package["memory_name"])
            self.memory = np.ndarray((self.buffer_size, self.frame_size), dtype=self.dtype, buffer=self.shm_memory.buf)
        else:
            self.shm_memory = None
            self.memory = np.zeros((self.buffer_size, self.frame_size), dtype=self.dtype)

        self.read_flag = shm_package["read_flag"]
        self.write_flag = shm_package["write_flag"]
        self.read_lock = shm_package["read_lock"]
        self.write_lock = shm_package["write_lock"]
        self.reset()

    def reset(self) -> None:
        with self.write_lock:
            with self.read_lock:
                self.read_flag.value = 0
                self.write_flag.value = 0

    def empty(self) -> bool:
        return self.write_flag.value == self.read_flag.value

    def full(self) -> bool:
        return (self.write_flag.value + 1) % self.buffer_size == self.read_flag.value

    def get(self) -> np.ndarray:
        if self.empty():
            return np.zeros(self.frame_size, dtype=self.dtype)

        data = self.memory[self.read_flag.value, :].copy()
        with self.read_lock:
            self.read_flag.value = (self.read_flag.value + 1) % self.buffer_size
        return data

    def put(self, data: np.ndarray, regardless: bool = False) -> None:
        if self.full() and not regardless:
            return

        self.memory[self.write_flag.value, :] = data
        with self.write_lock:
            self.write_flag.value = (self.write_flag.value + 1) % self.buffer_size

class ServerUserSocket:
    """An object representing free or occupied slot for tablet
    :ivar main_server: the main server reference
    :type main_server: MainServer
    :ivar ip_address: the IP address of the user
    :type ip_address: str | None
    :ivar port: the port number of the user
    :type port: int | None
    :ivar name: the name of the user
    :type name: str | None
    :ivar __active: free/occupied flag
    :type __active: bool
    :ivar received_audio_buffer: the received audio buffer
    :type received_audio_buffer: RingBuffer
    """

    def __init__(self, main_server: MainServer, ring_buffer: RingBuffer) -> None:
        """Constructor for ServerUserSocket
        :param main_server: the main server reference
        :type main_server: MainServer
        :param ring_buffer: the RingBuffer for received audio"""
        self.main_server = main_server
        self.ip_address = None
        self.port = None
        self.name = None
        self.__active = False
        self.received_audio_buffer = ring_buffer

    def switch_on(self, ip_address: str, port: int, name: str | None = None) -> None:
        """Assigns tablet to the slot
        :param ip_address: the IP address of the user
        :type ip_address: str
        :param port: the port number of the user
        :type port: int
        :param name: the name of the user
        :type name: str | None"""
        self.ip_address = ip_address
        self.port = port
        self.name = "unknown" if name is None else name
        self.__active = True

    def switch_off(self) -> None:
        """Frees and cleans the slot"""
        self.__active = False

    def is_active(self) -> bool:
        """Returns if the slot is free or not"""
        return self.__active

    def udp_address(self) -> tuple[str, int]:
        """Returns full UDP address of tablet"""
        return self.ip_address, self.port

    def __repr__(self) -> str:
        if self.is_active():
            return f"({self.name}, ({self.ip_address}, {self.port}))"
        return "(empty)"


async def AudioTransmitter(main_server: MainServer) -> None:
    """Sends audio only to authorized tablets (Downlink Routing)"""
    monitor.log_event("TRANSMITTER_START", message="Audio Transmitter task active")

    while main_server.is_running():
        with monitor.time_operation("TRANSMISSION_LATENCY", level="DEBUG"):
            for i in range(main_server.channels):
                if not main_server.transmitted_audio_buffers[i].empty():
                    data = main_server.transmitted_audio_buffers[i].get().tobytes()
                    authorized_ips = main_server.downlink_routing[i]

                    for j in range(main_server.max_users):
                        socket = main_server.user_sockets[j]
                        if socket.is_active() and socket.ip_address in authorized_ips:
                            try:
                                main_server.udp_transport.sendto(data, socket.udp_address())
                            except OSError as exc:
                                monitor.log_error("NETWORK_SEND_FAIL", exc,
                                                  {"target_ip": socket.ip_address, "channel": i},
                                                  message=f"OS failed to send UDP packet to {socket.ip_address}")
                            await asyncio.sleep(0)

        await asyncio.sleep(0.001)


class AudioReceiver(asyncio.DatagramProtocol):
    """Receives audio from the tablets
    :ivar main_server: the main server object
    :type main_server: MainServer
    :ivar transport: the asyncio.DatagramTransport object
    :type transport: asyncio.DatagramTransport | None"""

    def __init__(self, main_server: MainServer) -> None:
        self.transport = None
        super().__init__()
        self.main_server = main_server

    def connection_made(self, transport):
        """Function called once, when datagram endpoint is created
        :param transport: the asyncio.DatagramTransport object
        :ivar transport: asyncio.DatagramTransport"""
        self.transport = transport
        monitor.log_event("UDP_READY", message="Datagram transport established")

    def datagram_received(self, data, addr):
        """A callback called when new data arrives
        :param data: an incoming audio data
        :type data: bytes
        :param addr: a tablet IP address
        :type addr: tuple[str, int]"""
        found = False
        for i in range(self.main_server.max_users):
            if self.main_server.user_sockets[i].udp_address() == addr:
                data = np.frombuffer(data, dtype=np.float32)
                self.main_server.user_sockets[i].received_audio_buffer.put(data, regardless=True)
                found = True
                break
        if not found:
            monitor.log_event("UNKNOWN_SOURCE_AUDIO",
                              {"source_addr": addr},
                              level="WARNING",
                              message=f"Unauthorized audio packet received from {addr}")


async def AudioTester(main_server: MainServer, i: int, j: int) -> None:
    """Async task for testing purposes
    :param main_server: the main server object
    :type main_server: MainServer
    :param i: the index of the sender
    :type i: int
    :param j: the index of the receiver
    :type j: int"""
    print(f"AudioTester ready")
    while main_server.is_running():
        if not main_server.user_sockets[i].received_audio_buffer.empty():
            data = main_server.user_sockets[i].received_audio_buffer.get()
            main_server.transmitted_audio_buffers[j].put(data, regardless=True)
        await asyncio.sleep(0)
    print(f"AudioTester closed")

"""async def LoadObserver(main_server: MainServer) -> None:
    Monitors server load
    :param main_server: the main server object
    :type main_server: MainServer
    print(f"LoadObserver ready")
    while main_server.is_running():
        break
    print(f"LoadObserver closed")"""


class MainServer:
    """
    Mission Control Hub - High-performance Audio Summing Server.
    Acts as a passive executor for the Mission Control Manager.
    """

    def __init__(self, config_file: str | dict, radio_output_packages: list[dict],
                 unused_uplink: list = None):

        if isinstance(config_file, str):
            with open(config_file, "r", encoding="utf-8") as config_json:
                config = json.load(config_json)
        else:
            config = config_file
        check_config(config)

        self.config = config_file if isinstance(config_file, dict) else json.load(open(config_file))

        self.channels = config["channels"]
        self.max_users = config["max_users"]
        self.ip_address = config["ip_address"]
        self.communication_port = config["communication_port"]
        self.remote_communication_port = config["remote_communication_port"]
        self.audio_chunk_size = config["audio_chunk_size"]

        self.user_sockets = []
        for i in range(self.max_users):
            local_pkg = {
                "buffer_size": 10,
                "frame_size": self.audio_chunk_size,
                "memory_name": None,
                "read_flag": mp.Value('i', 0),
                "write_flag": mp.Value('i', 0),
                "read_lock": mp.Lock(),
                "write_lock": mp.Lock(),
                "dtype": np.float32
            }
            self.user_sockets.append(ServerUserSocket(self, RingBuffer(local_pkg)))

        self.transmitted_audio_buffers = [RingBuffer(radio_output_packages[i])
                                          for i in range(self.channels)]

        self.uplink_routing = {i: set() for i in range(self.channels)}
        self.downlink_routing = {i: set() for i in range(self.channels)}
        self.headroom_lin = 10.0 ** (-12.0 / 20.0)

        self.udp_transport = None
        self.loop = None
        self.__RUN = False
        self.__STATE = "off"


    def execute_manager_command(self, command_packet: dict) -> None:
        """
        Main entry point for instructions coming from the Manager API.
        CMD 1: Downlink (not implemented in this summing logic)
        CMD 2: Uplink (Tablet -> Radio)
        """
        cmd = command_packet.get("command")
        data = command_packet.get("data")

        if cmd == 1:
            ch_idx = data["channel"]
            ip = data["user_ip"]
            status = data["status"]
            if 0 <= ch_idx < self.channels:
                if status >= 1:
                    self.downlink_routing[ch_idx].add(ip)
                else:
                    self.downlink_routing[ch_idx].discard(ip)
                print(f"HUB: Downlink Updated - Channel {ch_idx} listeners: {self.downlink_routing[ch_idx]}")
                monitor.log_event("ROUTING_DOWNLINK", {"ch": ch_idx, "ip": ip, "status": status},
                                  message=f"Downlink change for {ip}")

        elif cmd == 2:
            ch_idx = data["channel"]
            ip = data["user_ip"]
            status = data["status"]
            if 0 <= ch_idx < self.channels:
                if status == 1:
                    self.uplink_routing[ch_idx].add(ip)
                else:
                    self.uplink_routing[ch_idx].discard(ip)
                print(f"HUB: Uplink Updated - Channel {ch_idx} speakers: {self.uplink_routing[ch_idx]}")
                monitor.log_event("ROUTING_UPLINK", {"ch": ch_idx, "ip": ip, "status": status},
                                  message=f"Uplink change for {ip}")

    def reset_internal_state(self) -> None:
        """Clears all routing and resets ring buffers for a clean restart."""
        monitor.log_event("SYSTEM_RESET", level="WARN", message="Internal hub state reset initiated")
        self.uplink_routing = {i: set() for i in range(self.channels)}
        for buf in self.transmitted_audio_buffers:
            buf.reset()
        for socket in self.user_sockets:
            if socket.received_audio_buffer:
                socket.received_audio_buffer.reset()
        print("HUB: Internal state and buffers reset.")


    def is_running(self) -> bool:
        return self.__RUN

    def state(self) -> str:
        return self.__STATE

    def stop(self) -> None:
        self.__RUN = False
        self.__STATE = "off"

    async def initiate_server(self) -> None:
        self.__STATE = "startup"

        transport, _ = await self.loop.create_datagram_endpoint(
            lambda: AudioReceiver(self),
            local_addr=(self.ip_address, self.communication_port))

        self.udp_transport = transport
        monitor.log_event("HUB_INIT",
                          {"ip": self.ip_address, "port": self.communication_port},
                          message=f"UDP Audio Receiver active on {self.ip_address}:{self.communication_port}")

        self.loop.create_task(AudioTransmitter(self))
        self.loop.create_task(self.summing_mixer_loop())

        self.__RUN = True
        self.__STATE = "on"

    async def summing_mixer_loop(self) -> None:
        """
        The Engine: Sums all active tablet streams into radio channels.
        High-frequency loop (~5ms) with latency tracking.
        """
        monitor.log_event("MIXER_START", message="Summing Mixer Engine started.")
        while self.__RUN:
            with monitor.time_operation("AUDIO_SUMMING_LATENCY", level="DEBUG"):
                for ch_idx in range(self.channels):
                    active_ips = self.uplink_routing[ch_idx]
                    if not active_ips:
                        continue

                    composite_frame = np.zeros(self.audio_chunk_size, dtype=np.float32)
                    count = 0

                    for socket in self.user_sockets:
                        if socket.is_active() and socket.ip_address in active_ips:
                            if not socket.received_audio_buffer.empty():
                                frame = socket.received_audio_buffer.get()
                                composite_frame += frame
                                count += 1

                    if count > 0:
                        mixed_output = np.tanh(composite_frame * self.headroom_lin)
                        self.transmitted_audio_buffers[ch_idx].put(mixed_output, regardless=True)

            await asyncio.sleep(0.005)

    async def run(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        await self.initiate_server()
        while self.__RUN:
            await asyncio.sleep(0.1)
        await self.close_server()

    async def close_server(self) -> None:
        self.__STATE = "shutdown"
        if self.udp_transport is not None:
            self.udp_transport.close()
        monitor.log_event("HUB_SHUTDOWN", message="Server engine stopped and UDP transport closed")
        self.__STATE = "off"

    def get_user_id(self, udp_address: tuple[str, int]) -> int:
        for i in range(self.max_users):
            if self.user_sockets[i].is_active() and self.user_sockets[i].udp_address() == udp_address:
                return i
        raise KeyError(f"User {udp_address} not found")

    def add_user(self, udp_address: tuple[str, int], name: str | None = None) -> None:
        for i in range(self.max_users):
            if not self.user_sockets[i].is_active():
                self.user_sockets[i].switch_on(udp_address[0], udp_address[1], name)
                monitor.log_event("TABLET_CONNECTED", {"ip": udp_address[0], "slot": i},
                                  message=f"Tablet {udp_address[0]} added to slot {i}")
                return
        raise OverflowError("No free slots")

    def remove_user(self, udp_address: tuple[str, int]) -> None:
        monitor.log_event("TABLET_DISCONNECTED", {"ip": udp_address[0]}, message=f"Tablet {udp_address[0]} removed")
        user_id = self.get_user_id(udp_address)
        for ch in range(self.channels):
            self.uplink_routing[ch].discard(udp_address[0])
        self.user_sockets[user_id].switch_off()


def check_config(config: dict) -> None:
    """Checks the server's configuration from JSON file.
    :param config: server configuration
    :type config: dict
    """
    for param, ptype in [("max_users", int), ("channels", int), ("ip_address", str), ("communication_port", int),
                         ("transmitted_audio_buffer_size", int), ("received_audio_buffer_size", int),
                         ("remote_communication_port", int), ("audio_chunk_size", int)]:
        if param not in config:
            raise KeyError(f"Missing configuration parameter: {param}")
        if type(config[param]) != ptype:
            raise TypeError(f"{param} must be {ptype}, not {type(config[param])}")
