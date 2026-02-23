import asyncio
import json
import numpy as np
import multiprocessing as mp
from multiprocessing import shared_memory


class RingBuffer:
    def __init__(self, shm_package: dict, dtype=np.float32):
        self.buffer_size = shm_package["buffer_size"]
        self.frame_size = shm_package["frame_size"]
        self.shm_memory = shared_memory.SharedMemory(name=shm_package["memory_name"])
        self.memory = np.ndarray((self.buffer_size, self.frame_size), dtype=dtype, buffer=self.shm_memory.buf)
        self.read_flag = shm_package["read_flag"]  # flag is incremented, next data is read
        self.read_lock = shm_package["read_lock"]
        self.write_flag = shm_package["write_flag"]  # data is written, next flag is incremented
        self.write_lock = shm_package["write_lock"]
        self.read_flag = 0
        self.write_flag = 1

    def memory_name(self) -> str:
        return self.shm_memory.name

    def empty(self) -> bool:
        with self.write_lock:
            with self.read_lock:
                return self.write_flag == (self.read_flag + 1) % self.buffer_size

    def full(self) -> bool:
        with self.write_lock:
            with self.read_lock:
                return self.read_flag == self.write_flag

    def get(self) -> np.ndarray:
        if self.empty():
            raise Exception(f"Buffer empty")
        with self.read_lock:
            self.read_flag = (self.read_flag + 1) % self.buffer_size
        memory_copy = self.memory[self.read_flag, :].copy()
        return memory_copy

    def put(self, data: np.ndarray, regardless: bool = False) -> None:
        if self.full():
            if regardless:
                self.memory[self.read_flag, :] = data
                return
            raise Exception(f"Buffer full")
        self.memory[self.read_flag, :] = data
        with self.write_lock:
            self.write_flag = (self.write_flag + 1) % self.buffer_size


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

    def __init__(self, main_server: MainServer) -> None:
        """Constructor for ServerUserSocket
        :param main_server: the main server reference
        :type main_server: MainServer"""
        self.main_server = main_server
        self.ip_address = None
        self.port = None
        self.name = None
        self.__active = False
        self.received_audio_buffer = asyncio.Queue(maxsize=self.main_server.received_audio_buffer_size)
        # self.transmitted_audio_buffer = asyncio.Queue(maxsize=self.main_server.transmitted_audio_buffer_size)
        # self.audio_transmitter_task = None

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
        # self.priority = 0
        # self.received_audio_buffer = asyncio.Queue(maxsize=self.main_server.received_audio_buffer_size)
        # self.transmitted_audio_buffer = asyncio.Queue(maxsize=self.main_server.transmitted_audio_buffer_size)
        self.__active = True

    def switch_off(self) -> None:
        """Frees and cleans the slot"""
        self.__active = False
        # if self.audio_transmitter_task is not None:
        # self.audio_transmitter_task.cancel()

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

    async def AudioTransmitter(self) -> None:
        """Sends audio to the tablet"""
        print(f"AudioTransmitter for {self.ip_address} ready")
        try:
            while self.is_active() and self.main_server.is_running():
                data = await self.transmitted_audio_buffer.get()
                if self.is_active():
                    self.main_server.udp_transport.sendto(data, (self.ip_address, self.port))
                    # print(f"sent {self}")
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            print(f"AudioTransmitter for {self.ip_address} closed")
            raise


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
        print("AudioReceiver ready")

    def datagram_received(self, data, addr):
        """A callback called when new data arrives
        :param data: an incoming audio data
        :type data: bytes
        :param addr: a tablet IP address
        :type addr: tuple[str, int]"""
        try:
            for i in range(self.main_server.max_users):
                if self.main_server.user_sockets[i].udp_address() == addr:
                    if self.main_server.user_sockets[i].received_audio_buffer.full():
                        self.main_server.user_sockets[i].received_audio_buffer.get_nowait()
                    self.main_server.user_sockets[i].received_audio_buffer.put_nowait(data)
                    break
        except asyncio.QueueEmpty:
            pass
        except asyncio.QueueFull:
            pass


"""async def AudioTester(main_server: MainServer, i: int, j: int) -> None:
    Async task for testing purposes
    :param main_server: the main server object
    :type main_server: MainServer
    :param i: the index of the sender
    :type i: int
    :param j: the index of the receiver
    :type j: int
    print(f"AudioTester ready")
    while main_server.is_running():
        data = await main_server.user_sockets[i].received_audio_buffer.get()
        await main_server.user_sockets[j].transmitted_audio_buffer.put(data)
        # print("bridge")
    print(f"AudioTester closed")"""

"""async def LoadObserver(main_server: MainServer) -> None:
    Monitors server load
    :param main_server: the main server object
    :type main_server: MainServer
    print(f"LoadObserver ready")
    while main_server.is_running():
        break
    print(f"LoadObserver closed")"""


class MainServer:
    """An object representing server.
    :ivar max_users: the maximal number of users server can handle simultaneously
    :type max_users: int"""

    def __init__(self, config_file: str):

        # configuration parameters
        with open(config_file, "r", encoding="utf-8") as config_json:
            config = json.load(config_json)
        check_config(config)

        self.max_users = config["max_users"]
        self.ip_address = config["ip_address"]
        self.communication_port = config["communication_port"]
        self.remote_communication_port = config["remote_communication_port"]
        self.audio_chunk_size = config["audio_chunk_size"]
        self.received_audio_buffer_size = config["received_audio_buffer_size"]
        self.transmitted_audio_buffer_size = config["transmitted_audio_buffer_size"]

        self.user_sockets = [ServerUserSocket(self) for _ in range(self.max_users)]

        self.udp_transport = None
        self.loop = None
        # self.transmitted_audio_buffers = [asyncio.Queue(maxsize=self.transmitted_audio_buffer_size) for _ in range(self.max_users)]

        self.__RUN = False
        self.__READY = False

    def is_running(self) -> bool:
        """Checks if server is running"""
        return self.__RUN

    def stop(self) -> None:
        self.__RUN = False

    def is_stopped(self) -> bool:
        """Checks if server is stopped correctly"""
        return self.__READY

    async def initiate_server(self) -> None:
        """This function is called once when the server starts.
        :return None:"""
        print("Server started")
        self.__RUN = True
        self.__READY = False
        transport, _ = await self.loop.create_datagram_endpoint(
            lambda: AudioReceiver(self),
            local_addr=(self.ip_address, self.communication_port))
        self.udp_transport = transport
        # self.loop.create_task(LoadObserver(self))
        # for testing (start)
        # self.add_user(("127.0.0.1", 9100))
        # self.add_user(("127.0.0.1", 9101))
        # self.loop.create_task(AudioTester(self, 0, 0))
        # self.loop.create_task(AudioTester(self, 1, 1))
        # await asyncio.sleep(5)
        # self.remove_user(("127.0.0.1", 9100))
        # self.remove_user(("127.0.0.1", 9101))
        # for testing (end)

    async def main_server_loop(self) -> None:
        """This function is repeated in loop when server is running.
        :return None:"""
        pass

    async def close_server(self) -> None:
        """This function is called once when the server shuts down.
        :return None:"""
        if self.udp_transport is not None:
            self.udp_transport.close()
        self.__READY = True
        print("Server closed")

    async def run(self, loop: asyncio.AbstractEventLoop) -> None:
        """The body of the server, consists of initializing function, main loop and closing function.
        :return None:"""
        self.loop = loop
        await self.initiate_server()
        while self.__RUN:
            await self.main_server_loop()
            await asyncio.sleep(0)
        await self.close_server()

    def get_user_id(self, udp_address: tuple[str, int]) -> int:
        """Translates IP address to id of ServerUserSocket."""
        for i in range(self.max_users):
            if self.user_sockets[i].is_active() and self.user_sockets[i].udp_address() == udp_address:
                return i
        raise KeyError(f"User with address {udp_address} not found")

    def add_user(self, udp_address: tuple[str, int], name: str | None = None) -> None:
        """Adds a new active user to the list. If no free slot, raises an OverflowError.
        :param udp_address: the user to add
        :type udp_address: tuple[str, int]
        :param name: optional, the tablet name
        :return: user id on this server
        :rtype: int"""
        # if udp_address[0] in self.whitelist:
        for i in range(self.max_users):
            if not self.user_sockets[i].is_active():
                self.user_sockets[i].switch_on(udp_address[0], udp_address[1], name)
                # task = self.loop.create_task(self.user_sockets[i].AudioTransmitter())
                # self.user_sockets[i].audio_transmitter_task = task
                print(f"User added: {self.user_sockets[i]}")
                return
        raise OverflowError(f"No free user slot for user {udp_address}")
        # raise ConnectionRefusedError(f"User {udp_address} not on the whitelist")

    def remove_user(self, udp_address: tuple[str, int]) -> None:
        """Removes active user, freeing the slot. If no such user exists, raises a KeyError.
        :param udp_address: the user to add
        :type udp_address: tuple[str, int]
        :return: None"""
        user_id = self.get_user_id(udp_address)
        self.user_sockets[user_id].switch_off()
        print(f"User removed: {udp_address}")

    """def change_priority(self, udp_address: tuple[str, int], priority: int) -> None:
        Change the user's priority. If no such user exists, raises a KeyError.
        :param udp_address: the user to add
        :type udp_address: tuple[str, int]
        :param priority: the new priority
        :type priority: int
        :return: None
        user_id = self.get_user_id(udp_address)
        self.user_sockets[user_id].priority = priority
        print(f"User removed: {udp_address}")"""


def check_config(config: dict) -> None:
    """Checks the server's configuration from JSON file.
    :param config: server configuration
    :type config: dict
    """
    for param, ptype in [("max_users", int), ("ip_address", str), ("communication_port", int),
                         ("transmitted_audio_buffer_size", int), ("received_audio_buffer_size", int),
                         ("remote_communication_port", int), ("audio_chunk_size", int)]:
        if param not in config:
            raise KeyError(f"Missing configuration parameter: {param}")
        if type(config[param]) != ptype:
            raise TypeError(f"{param} must be {ptype}, not {type(config[param])}")
