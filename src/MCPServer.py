import asyncio
import json
# from enum import Enum


class ServerUserSocket:
    """An object representing free or occupied slot for tablet
    :ivar main_server: the main server reference
    :type main_server: MainServer
    :ivar ip_address: the IP address of the user
    :type ip_address: str | None
    :ivar port: the port number of the user
    :type port: int | None
    :ivar __active: free/occupied flag
    :type __active: bool
    :ivar received_audio_buffer: the received audio buffer
    :type received_audio_buffer: asyncio.Queue
    :ivar transmitted_audio_buffer: the transmitted audio buffer
    :type transmitted_audio_buffer: asyncio.Queue
    :ivar audio_transmitter_task: the task in asyncio loop for data downlink
    :type audio_transmitter_task: asyncio.Task | None
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
        self.transmitted_audio_buffer = asyncio.Queue(maxsize=self.main_server.transmitted_audio_buffer_size)
        self.audio_transmitter_task = None

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
        self.received_audio_buffer = asyncio.Queue(maxsize=self.main_server.received_audio_buffer_size)
        self.transmitted_audio_buffer = asyncio.Queue(maxsize=self.main_server.transmitted_audio_buffer_size)
        self.__active = True

    def switch_off(self) -> None:
        """Frees and cleans the slot"""
        self.__active = False
        if self.audio_transmitter_task is not None:
            self.audio_transmitter_task.cancel()

    def active(self) -> bool:
        """Returns if the slot is free or not"""
        return self.__active

    def udp_address(self) -> tuple[str, int]:
        """Returns full UDP address of tablet"""
        return self.ip_address, self.port

    def __repr__(self) -> str:
        if self.active():
            return f"({self.name}, ({self.ip_address}, {self.port}))"
        return "(empty)"

    async def AudioTransmitter(self) -> None:
        """Sends audio to the tablet"""
        print(f"AudioTransmitter for {self.ip_address} ready")
        try:
            while self.active() and self.main_server.is_running():
                data = await self.transmitted_audio_buffer.get()
                if self.active():
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
        data = await main_server.user_sockets[i].received_audio_buffer.get()
        await main_server.user_sockets[j].transmitted_audio_buffer.put(data)
        # print("bridge")
    print(f"AudioTester closed")


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
        # self.transmitted_audio_buffers = [asyncio.Queue(maxsize=self.transmitted_audio_buffer_size) for _ in range(self.max_users)]

        # self.downlink_routing_table = [[RoutingStatus.DISCONNECTED for _ in range(self.max_users)] for _ in
        # range(self.channels)]
        # self.uplink_routing_table = [[RoutingStatus.DISCONNECTED for _ in range(self.max_users)] for _ in
        # range(self.channels)]

        self.__RUN = True
        self.__STOPPED = False
        self.loop = None

    def is_running(self) -> bool:
        """Checks if server is running"""
        return self.__RUN

    def is_stopped(self) -> bool:
        """Checks if server is stopped correctly"""
        return self.__STOPPED

    async def initiate_server(self) -> None:
        """This function is called once when the server starts.
        :return None:"""
        print("Server started")
        self.__STOPPED = False
        transport, protocol = await self.loop.create_datagram_endpoint(
            lambda: AudioReceiver(self),
            local_addr=(self.ip_address, self.communication_port))
        self.udp_transport = transport
        # for testing (start)
        self.add_user(("127.0.0.1", 9100))
        self.add_user(("127.0.0.1", 9101))
        self.loop.create_task(AudioTester(self, 0, 0))
        self.loop.create_task(AudioTester(self, 1, 1))
        await asyncio.sleep(5)
        self.remove_user(("127.0.0.1", 9100))
        self.remove_user(("127.0.0.1", 9101))
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
        self.__STOPPED = True
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
            if self.user_sockets[i].active() and self.user_sockets[i].udp_address() == udp_address:
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
            if not self.user_sockets[i].active():
                self.user_sockets[i].switch_on(udp_address[0], udp_address[1], name)
                task = self.loop.create_task(self.user_sockets[i].AudioTransmitter())
                self.user_sockets[i].audio_transmitter_task = task
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
        if self.user_sockets[user_id].active() and self.user_sockets[user_id].udp_address() == udp_address:
            self.user_sockets[user_id].switch_off()
            print(f"User removed: {udp_address}")

        # def set_downlink_routing_status(self, channel: int, user: ServerUser, status: RoutingStatus) -> None:
        """Change user's status in downlink routing table.
        :param channel: channel's number
        :type channel: int
        :param user: user to change status
        :type channel: ServerUser
        :param status: new user's status
        :type channel: RoutingStatus
        :return None:"""
        """if channel not in range(self.channels):
            raise ValueError(f"Channel {channel} is incorrect")
        if not isinstance(user, ServerUser):
            raise TypeError(f"User must be type ServerUser, not {type(user)}")
        if not isinstance(status, RoutingStatus):
            raise TypeError(f"Status must be type RoutingStatus, not {type(status)}")
        for i in range(self.max_users):
            with self.lock_bank.active_users_lock:
                if type(self.active_users[i]) == ServerUser and self.active_users[i] == user:
                    with self.lock_bank.downlink_routing_lock:
                        self.downlink_routing_table[channel][i] = status
                    return
        raise KeyError(f"User {user} not found")"""

        # def set_uplink_routing_status(self, channel: int, user: ServerUser, status: RoutingStatus) -> None:
        """Change user's status in uplink routing table.
        :param channel: channel's number
        :type channel: int
        :param user: user to change status
        :type channel: ServerUser
        :param status: new user's status
        :type channel: RoutingStatus
        return: None"""
        """if channel not in range(self.channels):
            raise ValueError(f"Channel {channel} is incorrect")
        if not isinstance(user, ServerUser):
            raise TypeError(f"User must be type ServerUser, not {type(user)}")
        if not isinstance(status, RoutingStatus):
            raise TypeError(f"Status must be type RoutingStatus, not {type(status)}")
        for i in range(self.max_users):
            with self.lock_bank.active_users_lock:
                if type(self.active_users[i]) == ServerUser and self.active_users[i] == user:
                    with self.lock_bank.downlink_routing_lock:
                        self.uplink_routing_table[channel][i] = status
                    return
        raise KeyError(f"User {user} not found")"""

    """def execute_manager_command(self, command: dict) -> None:
        if self.manager_command_buffer.full():
            discard = self.manager_command_buffer.get_nowait()
            raise Full(f"Manager command buffer overflow, discarded: {discard}")
        self.manager_command_buffer.put_nowait({"command": 1, "data": command})

    def audio_to_buffer(self, audio_chunk: bytes, channel: int) -> None:
        if channel not in range(self.channels):
            raise ValueError(f"Channel {channel} is incorrect")
        self.transmitted_audio_buffers[channel].put_nowait(audio_chunk)

    def audio_from_buffer(self, user_ip: str) -> bytes:
        with self.lock_bank.active_users_lock:
            for i in range(self.max_users):
                if self.active_users[i] is not None and self.active_users[i].ip_address == user_ip:
                    return self.received_audio_buffers[i].get_nowait()
        raise KeyError(f"User {user_ip} not found")"""


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
