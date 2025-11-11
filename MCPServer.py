import websockets
from websockets.sync.server import serve
import threading
import json
import numpy as np
import sounddevice as sd
from test.MCPTesting import DEFAULT_COMMAND_SET, ServerInterruptMockup
from src.MCPClient import ServerUser
from enum import Enum


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


class MainServer:
    """An object representing server.
    :ivar __max_users: the maximal number of users server can handle simultaneously
    :type __max_users: int
    :ivar __active_users: an array of references to active users object instances
    :type __active_users: list[ServerUser | None]
    :ivar __active_threads: a set of threads to stop once the server is shut down
    :type __active_threads: set[threading.Thread]
    :ivar __command_set: a list of commands sent from client to the server
    :type __command_set: list[Callable]
    :ivar __downlink_routing_table: permission for listening to channels
    :type __downlink_routing_table: list[list[RoutingStatus]]
    :ivar __uplink_routing_table: permission for talking on channels
    :type __uplink_routing_table: list[list[RoutingStatus]]"""

    # A reference for running MainServer instance
    MAIN_SERVER = None

    def __init__(self):
        self.STOP_SERVER = threading.Event()
        self.__max_users = 2
        self.__channels = 4
        self.__active_users = [None for _ in range(self.__max_users)]
        self.__active_threads = set()
        self.__command_set = DEFAULT_COMMAND_SET
        self.__downlink_routing_table = [[RoutingStatus.DISCONNECTED for _ in range(self.__max_users)] for _ in
                                         range(self.__channels)]
        self.__uplink_routing_table = [[RoutingStatus.DISCONNECTED for _ in range(self.__max_users)] for _ in
                                       range(self.__channels)]
        self.communication_port = 9000
        self.lock_bank = ServerLockBank()
        MainServer.MAIN_SERVER = self

    def initiate_server(self) -> None:
        """This function is called once when the server starts.
        :return None:"""
        print("Server started")
        server_listener = ServerListener()
        server_listener.start()
        self.add_thread(server_listener)
        # for testing purposes only
        server_interrupt_mockup = ServerInterruptMockup(MainServer.MAIN_SERVER)
        server_interrupt_mockup.start()
        self.add_thread(server_interrupt_mockup)

    def main_server_loop(self) -> None:
        """This function is repeated in loop when server is running.
        :return None:"""
        pass

    def close_server(self) -> None:
        """This function is called once when the server shuts down.
        :return None:"""
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
        for i in range(self.__max_users):
            with self.lock_bank.active_threads_lock:
                if self.__active_users[i] is None:
                    self.__active_users[i] = user
                    return i
        raise OverflowError("Too many users")

    def remove_user(self, user: ServerUser) -> None:
        """Removes active user, freeing the slot. If no such user exists, raises a KeyError.
        :param user: the user to remove
        :type user: ServerUser
        :return: None"""
        for i in range(self.__max_users):
            with self.lock_bank.active_threads_lock:
                if type(self.__active_users[i]) == ServerUser and self.__active_users[i].id == user.id:
                    self.__active_users[i] = None
                    return
        raise KeyError(f"User {user.id} not found")

    def set_downlink_routing_status(self, channel: int, user:ServerUser, status: RoutingStatus) -> None:
        """Change user's status in downlink routing table.
        :param channel: channel's number
        :type channel: int
        :param user: user to change status
        :type channel: ServerUser
        :param status: new user's status
        :type channel: RoutingStatus
        "return None:"""
        if channel not in range(self.__channels):
            raise ValueError(f"Channel {channel} is incorrect")
        if not isinstance(user, ServerUser):
            raise TypeError(f"User must be type ServerUser, not {type(user)}")
        if not isinstance(status, RoutingStatus):
            raise TypeError(f"Status must be type RoutingStatus, not {type(status)}")
        for i in range(self.__max_users):
            with self.lock_bank.active_users_lock:
                if type(self.__active_users[i]) == ServerUser and self.__active_users[i].id == user.id:
                    self.__downlink_routing_table[channel][i] = status
                    return
        raise KeyError(f"User {user.id} not found")

    def set_uplink_routing_status(self, channel: int, user:ServerUser, status: RoutingStatus) -> None:
        """Change user's status in uplink routing table.
        :param channel: channel's number
        :type channel: int
        :param user: user to change status
        :type channel: ServerUser
        :param status: new user's status
        :type channel: RoutingStatus
        return: None"""
        if channel not in range(self.__channels):
            raise ValueError(f"Channel {channel} is incorrect")
        if not isinstance(user, ServerUser):
            raise TypeError(f"User must be type ServerUser, not {type(user)}")
        if not isinstance(status, RoutingStatus):
            raise TypeError(f"Status must be type RoutingStatus, not {type(status)}")
        for i in range(self.__max_users):
            with self.lock_bank.active_users_lock:
                if type(self.__active_users[i]) == ServerUser and self.__active_users[i].id == user.id:
                    self.__uplink_routing_table[channel][i] = status
                    return
        raise KeyError(f"User {user.id} not found")


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
        with serve(user_handler, "localhost", MainServer.MAIN_SERVER.communication_port) as server_listener:
            self.server_listener = server_listener
            server_listener.serve_forever()

    def stop(self) -> None:
        """A program thread doing when server is stopped.
        :return None:"""
        self.server_listener.shutdown()
        print(f"Thread {self} stopped")


def user_handler(websocket: websockets.sync.server.ServerConnection) -> None:
    """Function called every time a new client is connected. Works in a loop until client disconnects or server shuts down.
    :param websocket: an object representing a connection with one client
    :type websocket: websockets.sync.server.ServerConnection
    :return None:"""
    user = ServerUser()
    try:
        iden = MainServer.MAIN_SERVER.add_user(user)
    except OverflowError:
        print("Client cannot connected: too many users")
        response = json.dumps({"command": -1, "result": None})
        websocket.send(response)
        return
    user.id = iden
    print(f"Client <{user.id}, {user.name}> connected")
    instruction_list = DEFAULT_COMMAND_SET
    try:
        for message in websocket:
            if MainServer.MAIN_SERVER.STOP_SERVER.is_set():
                raise InterruptedError()
            if isinstance(message, str):
                message = json.loads(message)
                if "command" in message:
                    result = instruction_list[message["command"]](message["data"])
                    response = json.dumps({"command": message["command"], "result": result})
                else:
                    response = json.dumps({"command": -1, "result": None})
                websocket.send(response)
            elif isinstance(message, bytes):
                websocket.send("Sound received")
                sd.play(np.frombuffer(message, dtype='int16'), samplerate=44100)
                sd.wait()
            else:
                raise TypeError(f"Incorrect message type: {type(message)}")
    except websockets.exceptions.ConnectionClosedOK:
        print("Client disconnected correctly")
    except websockets.exceptions.ConnectionClosedError:
        print("Client disconnected incorrectly")
    except InterruptedError:
        print("Disconnected due to server stopping")
    except TypeError as exception:
        print(exception)
    finally:
        try:
            MainServer.MAIN_SERVER.remove_user(user)
        except KeyError as exception:
            print(exception)


def main() -> None:
    control_panel_server = MainServer()
    control_panel_server.run()


if __name__ == "__main__":
    main()
