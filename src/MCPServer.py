import websockets
from websockets.sync.server import serve
import threading
import json
from test.MCPTesting import ServerInterruptMockup, AudioPlayer
from enum import Enum
from queue import Queue, Full, Empty
import socket


class ServerUser:
    def __init__(self, ip_addr: str, port: int, websocket: websockets.sync.server.ServerConnection,
                 server_id: int | None = None, name: str | None = None):
        self.server_id = server_id
        self.name = name
        if not ip_addr in MainServer.MAIN_SERVER.whitelist:
            raise ValueError(f"Invalid IP address - {ip_addr}")
        self.ip_address = ip_addr
        self.udp_address = (ip_addr, port)
        self.websocket = websocket

    def __repr__(self) -> str:
        return f"({self.name}, {self.ip_address})"

    def __eq__(self, other) -> bool:
        return self.ip_address == other.ip_address

    def close_websocket(self) -> None:
        self.websocket.close()


def client_instruction0(data: str, user: ServerUser) -> None:
    """Instruction 0 - set a user's name
    :param data: user's new name
    :type data: str
    :param user: user object
    :type user: ServerUser
    :return: None"""
    if not isinstance(data, str):
        raise TypeError(f"Instruction 0 - data must be str, not {type(data)}")
    user.name = data
    # print(user)


def client_instruction1(data: dict, user: ServerUser) -> None:
    """Instruction 1 - a PTT request"""
    if MainServer.MAIN_SERVER.server_request_buffer.full():
        discard = MainServer.MAIN_SERVER.server_request_buffer.get_nowait()
        raise Full(f"Buffer overflow, discarded: {discard}")
    MainServer.MAIN_SERVER.server_request_buffer.put_nowait({"command": 1, "data": data})


def client_instruction2(data, user: ServerUser):
    """Instruction 2 - a test ping"""
    return data


DEFAULT_CLIENT_COMMAND_SET = [client_instruction0, client_instruction1, client_instruction2]


def check_user_ip(data: dict) -> int:
    user_ip = data['user_ip']
    user = None
    with MainServer.MAIN_SERVER.lock_bank.active_users_lock:
        for i in range(MainServer.MAIN_SERVER.max_users):
            if MainServer.MAIN_SERVER.active_users[i].ip_address == user_ip:
                user = i
                break
    if user is None:
        raise KeyError(f"Did not find user: {user_ip}")
    return user


def manager_instruction0(data) -> None:
    """Instruction 0 - stop the server"""
    MainServer.MAIN_SERVER.STOP_SERVER.set()
    return


def manager_instruction1(data: dict) -> None:
    """Instruction 1 - change downlink routing status"""
    user = check_user_ip(data)
    channel = data['channel']
    status = RoutingStatus(data['status'])
    with MainServer.MAIN_SERVER.lock_bank.downlink_routing_lock:
        MainServer.MAIN_SERVER.downlink_routing_table[channel][user] = status
    return


def manager_instruction2(data: dict) -> None:
    """Instruction 2 - change uplink routing status"""
    user = check_user_ip(data)
    channel = data['channel']
    status = RoutingStatus(data['status'])
    with MainServer.MAIN_SERVER.lock_bank.uplink_routing_lock:
        MainServer.MAIN_SERVER.uplink_routing_table[channel][user] = status
    return


DEFAULT_MANAGER_COMMAND_SET = [manager_instruction0, manager_instruction1, manager_instruction2]


class RoutingStatus(Enum):
    DISCONNECTED = 0
    CONNECTED = 1
    PRIORITY = 2


class ServerLockBank:
    """A bunch of locks for MainServer for critical resources' protection.
    :ivar active_users_lock: locks MainServer.__active_users
    :type active_users_lock: threading.Lock
    :ivar active_threads_lock: locks MainServer.__active_threads
    :type active_threads_lock: threading.Lock"""

    def __init__(self):
        self.active_users_lock = threading.Lock()
        self.active_threads_lock = threading.Lock()
        self.downlink_routing_lock = threading.Lock()
        self.uplink_routing_lock = threading.Lock()


class MainServer:
    """An object representing server.
    :ivar max_users: the maximal number of users server can handle simultaneously
    :type max_users: int
    :ivar active_users: an array of references to active users object instances
    :type active_users: list[ServerUser | None]
    :ivar __active_threads: a set of threads to stop once the server is shut down
    :type __active_threads: set[threading.Thread]
    :ivar client_command_set: a list of commands sent from client to the server
    :type client_command_set: list[Callable]
    :ivar downlink_routing_table: permission for listening to channels
    :type downlink_routing_table: list[list[RoutingStatus]]
    :ivar uplink_routing_table: permission for talking on channels
    :type uplink_routing_table: list[list[RoutingStatus]]"""

    # A reference for running MainServer instance
    MAIN_SERVER = None

    def __init__(self, config_file: str):
        with open(config_file, "r", encoding="utf-8") as config_json:
            config = json.load(config_json)
        check_config(config)
        self.STOP_SERVER = threading.Event()
        self.max_users = config["max_users"]
        self.channels = config["channels"]
        self.active_users = [None for _ in range(self.max_users)]
        self.whitelist = config["whitelist"]
        self.received_audio_buffers = [Queue(maxsize=config["received_audio_buffer_size"]) for _ in
                                       range(self.max_users)]
        self.transmitted_audio_buffers = [Queue(maxsize=config["transmitted_audio_buffer_size"]) for _ in
                                          range(self.channels)]
        self.manager_command_buffer = Queue(maxsize=config["manager_command_buffer_size"])
        self.server_request_buffer = Queue(maxsize=config["server_request_buffer_size"])
        self.__active_threads = set()
        self.client_command_set = DEFAULT_CLIENT_COMMAND_SET
        self.__manager_command_set = DEFAULT_MANAGER_COMMAND_SET
        self.downlink_routing_table = [[RoutingStatus.DISCONNECTED for _ in range(self.max_users)] for _ in
                                       range(self.channels)]
        self.uplink_routing_table = [[RoutingStatus.DISCONNECTED for _ in range(self.max_users)] for _ in
                                     range(self.channels)]
        self.ip_address = config["ip_address"]
        self.communication_port = config["communication_port"]
        self.remote_communication_port = config["remote_communication_port"]
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.settimeout(1)
        self.udp_socket.bind((self.ip_address, self.communication_port))
        self.lock_bank = ServerLockBank()
        MainServer.MAIN_SERVER = self

    def initiate_server(self) -> None:
        """This function is called once when the server starts.
        :return None:"""
        print("Server started")
        server_listener = ServerListener()
        server_listener.start()
        self.add_thread(server_listener)
        audio_receiver = AudioReceiver(self.udp_socket)
        audio_receiver.start()
        self.add_thread(audio_receiver)
        audio_transmitter = AudioTransmitter(self.udp_socket)
        audio_transmitter.start()
        self.add_thread(audio_transmitter)
        # for testing purposes only
        """server_interrupt_mockup = ServerInterruptMockup(MainServer.MAIN_SERVER)
        server_interrupt_mockup.start()
        self.add_thread(server_interrupt_mockup)
        audio_player = AudioPlayer(MainServer.MAIN_SERVER)
        audio_player.start()
        self.add_thread(audio_player)
        with self.lock_bank.downlink_routing_lock:
            MainServer.MAIN_SERVER.downlink_routing_table[0][1] = RoutingStatus.CONNECTED
            MainServer.MAIN_SERVER.downlink_routing_table[1][0] = RoutingStatus.CONNECTED"""

    def main_server_loop(self) -> None:
        """This function is repeated in loop when server is running.
        :return None:"""
        if not self.manager_command_buffer.empty():
            line = self.manager_command_buffer.get()
            command, data = line["command"], line["data"]
            self.__manager_command_set[command](data)

    def close_server(self) -> None:
        """This function is called once when the server shuts down.
        :return None:"""
        # print(self.active_users)
        for user in self.active_users:
            if user is not None:
                self.remove_user(user)
                print(f"User {user} disconnected")
        # print(self.__active_threads)
        self.kill_all_threads()
        for thread in self.__active_threads:
            thread.join()
        print("Server closed")

    def run(self) -> None:
        """The body of the server, consists of initializing function, main loop and closing function.
        :return None:"""
        self.initiate_server()
        while not self.STOP_SERVER.is_set():
            self.main_server_loop()
        self.close_server()

    def add_thread(self, thread) -> None:
        """Adds a new active thread.
        :return None:"""
        with self.lock_bank.active_threads_lock:
            self.__active_threads.add(thread)

    def remove_thread(self, thread: threading.Thread) -> None:
        """Removes an active thread.
        :return None:"""
        with self.lock_bank.active_threads_lock:
            if thread in self.__active_threads:
                self.__active_threads.remove(thread)
            else:
                raise KeyError(f"User {thread} not found")

    def kill_all_threads(self) -> None:
        """Stops all active threads (most probably during server shutdown).
        :return None:"""
        with self.lock_bank.active_threads_lock:
            for thread in self.__active_threads:
                thread.stop()

    def add_user(self, user: ServerUser) -> int:
        """Adds a new active user to the list. If no free slot, raises an OverflowError.
        :param user: the user to add
        :type user: ServerUser
        :return: user id on this server
        :rtype: int"""
        for i in range(self.max_users):
            with self.lock_bank.active_users_lock:
                if self.active_users[i] is None:
                    self.active_users[i] = user
                    return i
        raise OverflowError("Too many users")

    def remove_user(self, user: ServerUser) -> None:
        """Removes active user, freeing the slot. If no such user exists, raises a KeyError.
        :param user: the user to remove
        :type user: ServerUser
        :return: None"""
        for i in range(self.max_users):
            with self.lock_bank.active_users_lock:
                if type(self.active_users[i]) == ServerUser and self.active_users[i] == user:
                    self.active_users[i].close_websocket()
                    self.active_users[i] = None
                    return
        raise KeyError(f"User {user} not found")

    def set_downlink_routing_status(self, channel: int, user: ServerUser, status: RoutingStatus) -> None:
        """Change user's status in downlink routing table.
        :param channel: channel's number
        :type channel: int
        :param user: user to change status
        :type channel: ServerUser
        :param status: new user's status
        :type channel: RoutingStatus
        :return None:"""
        if channel not in range(self.channels):
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
        raise KeyError(f"User {user} not found")

    def set_uplink_routing_status(self, channel: int, user: ServerUser, status: RoutingStatus) -> None:
        """Change user's status in uplink routing table.
        :param channel: channel's number
        :type channel: int
        :param user: user to change status
        :type channel: ServerUser
        :param status: new user's status
        :type channel: RoutingStatus
        return: None"""
        if channel not in range(self.channels):
            raise ValueError(f"Channel {channel} is incorrect")
        if not isinstance(user, ServerUser):
            raise TypeError(f"User must be type ServerUser, not {type(user)}")
        if not isinstance(status, RoutingStatus):
            raise TypeError(f"Status must be type RoutingStatus, not {type(status)}")
        for i in range(self.max_users):
            with self.lock_bank.active_users_lock:
                if type(self.active_users[i]) == ServerUser and self.active_users[i] == user:
                    with MainServer.MAIN_SERVER.lock_bank.downlink_routing_lock:
                        self.uplink_routing_table[channel][i] = status
                    return
        raise KeyError(f"User {user} not found")

    def execute_manager_command(self, command: dict) -> None:
        if self.manager_command_buffer.full():
            discard = self.manager_command_buffer.get_nowait()
            raise Full(f"Manager command buffer overflow, discarded: {discard}")
        self.manager_command_buffer.put_nowait({"command": 1, "data": command})



class ServerListener(threading.Thread):
    """A thread listening for new incoming connections.
    :ivar server_listener: a WebSocket server listening on certain port
    :type server_listener: websockets.sync.server.Server, None"""

    def __init__(self):
        super().__init__()
        self.server_listener = None

    def run(self) -> None:
        """A program thread running after start.
        :return None:"""
        with serve(user_handler, MainServer.MAIN_SERVER.ip_address,
                   MainServer.MAIN_SERVER.communication_port) as server_listener:
            self.server_listener = server_listener
            server_listener.serve_forever()

    def stop(self) -> None:
        """A program thread doing when server is stopped.
        :return None:"""
        self.server_listener.shutdown()
        print(f"Thread {self} stopped")


class AudioReceiver(threading.Thread):
    """A thread receiving and buffering audio data from users.
    :ivar udp_socket: a socket receiving audio from users
    :type udp_socket: socket.socket"""

    def __init__(self, udp_socket: socket.socket):
        super().__init__()
        self.is_active = True
        self.udp_socket = udp_socket

    def run(self) -> None:
        """A program thread running after start.
        :return None:"""
        while self.is_active:
            try:
                message, address = self.udp_socket.recvfrom(2048)
                header = address[0]
                with MainServer.MAIN_SERVER.lock_bank.active_users_lock:
                    for user in MainServer.MAIN_SERVER.active_users:
                        if user is not None and user.ip_address == header:
                            if MainServer.MAIN_SERVER.received_audio_buffers[user.server_id].full():
                                MainServer.MAIN_SERVER.received_audio_buffers[user.server_id].get_nowait()
                            MainServer.MAIN_SERVER.received_audio_buffers[user.server_id].put_nowait(message)
                            break
                    else:
                        print(f"Received package from unknown user: {address}")
            except Empty:
                pass
            except Full:
                pass
            except socket.timeout:
                pass
            except OSError as exc:
                print(exc)

    def stop(self) -> None:
        """A program thread executed when server is stopped.
        :return None:"""
        self.is_active = False
        print(f"Thread {self} stopped")


class AudioTransmitter(threading.Thread):
    """A thread transmitting an audio from channels to users.
    :ivar udp_socket: a socket transmitting audio to users
    :type udp_socket: socket.socket"""

    def __init__(self, udp_socket: socket.socket):
        super().__init__()
        self.is_active = True
        self.udp_socket = udp_socket

    def run(self) -> None:
        """A program thread running after start.
        :return None:"""
        while self.is_active:
            for i in range(MainServer.MAIN_SERVER.channels):
                # print("Getting audio from channel", i)
                if not MainServer.MAIN_SERVER.transmitted_audio_buffers[i].empty():
                    data = MainServer.MAIN_SERVER.transmitted_audio_buffers[i].get_nowait()
                    # print("Getting audio from channel", i)
                    for j in range(MainServer.MAIN_SERVER.max_users):
                        with MainServer.MAIN_SERVER.lock_bank.active_users_lock:
                            with MainServer.MAIN_SERVER.lock_bank.downlink_routing_lock:
                                if (MainServer.MAIN_SERVER.active_users[i] is not None
                                        and MainServer.MAIN_SERVER.downlink_routing_table[i][j]
                                        in [RoutingStatus.CONNECTED, RoutingStatus.PRIORITY]):
                                    self.udp_socket.sendto(data, MainServer.MAIN_SERVER.active_users[i].udp_address)

    def stop(self) -> None:
        """A program thread executed when server is stopped.
        :return None:"""
        self.is_active = False
        print(f"Thread {self} stopped")


def user_handler(websocket: websockets.sync.server.ServerConnection) -> None:
    """Function called every time a new client is connected. Works in a loop until client disconnects or server shuts down.
    :param websocket: an object representing a connection with one client
    :type websocket: websockets.sync.server.ServerConnection
    :return None:"""
    # print(websocket.remote_address)
    ip_addr, port = websocket.remote_address
    try:
        user = ServerUser(ip_addr, MainServer.MAIN_SERVER.remote_communication_port, websocket)
    except ValueError as exc:
        print(exc)
        return
    # print(user)
    try:
        iden = MainServer.MAIN_SERVER.add_user(user)
    except OverflowError:
        print("Client cannot connected: too many users")
        response = json.dumps({"command": -1, "result": None})
        websocket.send(response)
        return
    user.server_id = iden
    print(f"Client <{iden}, {user.name}> connected")
    try:
        for message in websocket:
            if MainServer.MAIN_SERVER.STOP_SERVER.is_set():
                raise InterruptedError()
            if isinstance(message, str):
                message = json.loads(message)
                if "command" in message:
                    try:
                        result = MainServer.MAIN_SERVER.client_command_set[message["command"]](message["data"], user)
                    except Full as exc:
                        print(exc)
                        response = json.dumps({"command": -1, "result": None})
                    else:
                        response = json.dumps({"command": message["command"], "result": result})
                else:
                    response = json.dumps({"command": -1, "result": None})
                websocket.send(response)
            else:
                raise TypeError(f"Incorrect message type: {type(message)}")
    except websockets.exceptions.ConnectionClosedOK:
        MainServer.MAIN_SERVER.remove_user(user)
        print("Client disconnected correctly")
    except websockets.exceptions.ConnectionClosedError:
        MainServer.MAIN_SERVER.remove_user(user)
        print("Client disconnected incorrectly")
    except InterruptedError:
        print("Disconnected due to server stopping")
    except TypeError as exc:
        print(exc)


def check_config(config: dict) -> None:
    """Checks the server's configuration from JSON file.
    :param config: server configuration
    :type config: dict
    """
    for param, ptype in [("max_users", int), ("channels", int), ("ip_address", str), ("communication_port", int),
                         ("transmitted_audio_buffer_size", int), ("received_audio_buffer_size", int),
                         ("manager_command_buffer_size", int), ("server_request_buffer_size", int),
                         ("remote_communication_port", int), ("whitelist", list)]:
        if param not in config:
            raise KeyError(f"Missing configuration parameter: {param}")
        if type(config[param]) != ptype:
            raise KeyError(f"{param} must be {ptype}, not {type(config[param])}")
