import asyncio
import json
import numpy as np


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
    """Sends audio to the tablets"""
    print(f"AudioTransmitter ready")
    while main_server.is_running():
        for i in range(main_server.channels):
            if not main_server.transmitted_audio_buffers[i].empty():
                data = main_server.transmitted_audio_buffers[i].get().tobytes()
                for j in range(main_server.max_users):
                    if not main_server.user_sockets[j].is_active():
                        continue
                    main_server.udp_transport.sendto(data, main_server.user_sockets[j].udp_address())
                    await asyncio.sleep(0)
        await asyncio.sleep(0)
    print(f"AudioTransmitter stopped")


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
        for i in range(self.main_server.max_users):
            if self.main_server.user_sockets[i].udp_address() == addr:
                data = np.frombuffer(data, dtype=np.float32)
                self.main_server.user_sockets[i].received_audio_buffer.put(data, regardless=True)
                # print(f"Received audio from {addr}")
                break


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
    """An object representing server.
    :ivar max_users: the maximal number of users server can handle simultaneously
    :type max_users: int"""

    def __init__(self, config_file: str | dict, downlink_buffers_packages: list[dict],
                 uplink_buffers_packages: list[dict]):

        # configuration parameters
        if isinstance(config_file, str):
            with open(config_file, "r", encoding="utf-8") as config_json:
                config = json.load(config_json)
        else:
            config = config_file
        check_config(config)

        self.max_users = config["max_users"]
        self.channels = config["channels"]
        self.ip_address = config["ip_address"]
        self.communication_port = config["communication_port"]
        self.remote_communication_port = config["remote_communication_port"]
        self.audio_chunk_size = config["audio_chunk_size"]
        self.received_audio_buffer_size = config["received_audio_buffer_size"]
        self.transmitted_audio_buffer_size = config["transmitted_audio_buffer_size"]

        self.user_sockets = [ServerUserSocket(self, RingBuffer(uplink_buffers_packages[i]))
                             for i in range(self.max_users)]
        self.transmitted_audio_buffers = [RingBuffer(downlink_buffers_packages[i]) for i in range(self.channels)]

        self.udp_transport = None
        self.loop = None

        self.__STOP = asyncio.Event()
        self.__STATE = "off"

    def is_running(self) -> bool:
        """Checks if server is running"""
        return not self.__STOP.is_set()

    def stop(self) -> None:
        self.__STOP.set()

    def state(self) -> str:
        """Checks if server is stopped correctly"""
        return self.__STATE

    async def initiate_server(self) -> None:
        """This function is called once when the server starts.
        :return None:"""
        print("Server started")
        self.__STATE = "startup"
        transport, _ = await self.loop.create_datagram_endpoint(
            lambda: AudioReceiver(self),
            local_addr=(self.ip_address, self.communication_port))
        self.udp_transport = transport
        self.loop.create_task(AudioTransmitter(self))
        self.__STOP.clear()
        self.__STATE = "on"
        # for testing (start)
        # self.loop.create_task(LoadObserver(self))
        # self.add_user(("127.0.0.1", 9100))
        # self.add_user(("127.0.0.1", 9101))
        self.loop.create_task(AudioTester(self, 0, 0))
        # self.loop.create_task(AudioTester(self, 1, 1))
        # await asyncio.sleep(5)
        # self.remove_user(("127.0.0.1", 9100))
        # self.remove_user(("127.0.0.1", 9101))
        # for testing (end)

    """async def main_server_loop(self) -> None:
        This function is repeated in loop when server is running.
        :return None:
        pass"""

    async def close_server(self) -> None:
        """This function is called once when the server shuts down.
        :return None:"""
        self.__STATE = "shutdown"
        if self.udp_transport is not None:
            self.udp_transport.close()
            print("AudioTransmitter closed")
        self.__STATE = "off"
        print("Server closed")

    async def run(self, loop: asyncio.AbstractEventLoop) -> None:
        """The body of the server, consists of initializing function, main loop and closing function.
        :return None:"""
        self.loop = loop
        await self.initiate_server()
        await self.__STOP.wait()
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
        for i in range(self.max_users):
            if not self.user_sockets[i].is_active():
                self.user_sockets[i].switch_on(udp_address[0], udp_address[1], name)
                print(f"User added: {self.user_sockets[i]}")
                return
        raise OverflowError(f"No free user slot for user {udp_address}")

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
    for param, ptype in [("max_users", int), ("channels", int), ("ip_address", str), ("communication_port", int),
                         ("transmitted_audio_buffer_size", int), ("received_audio_buffer_size", int),
                         ("remote_communication_port", int), ("audio_chunk_size", int)]:
        if param not in config:
            raise KeyError(f"Missing configuration parameter: {param}")
        if type(config[param]) != ptype:
            raise TypeError(f"{param} must be {ptype}, not {type(config[param])}")
