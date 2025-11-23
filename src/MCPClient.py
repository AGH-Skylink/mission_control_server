import websockets
from websockets.sync.server import serve
import json
import numpy as np
import sounddevice as sd
import socket


class ServerUser:
    def __init__(self, ip_addr: str, port: int, websocket: websockets.sync.server.ServerConnection,
                 server_id: int | None = None, name: str | None = None):
        self.server_id = server_id
        self.name = name
        if (len(ip_addr) < 10 or ip_addr[:10] != "192.168.0.") and ip_addr != "127.0.0.1":
            raise ValueError(f"Invalid IP address - {ip_addr}")
        self.websocket = websocket
        self.tcp_address = (ip_addr, port)
        self.udp_address = (ip_addr, None)
        header = bytes()
        for num in [int(x) for x in ip_addr.split(".")]:
            header += num.to_bytes(1, byteorder='little')
        self.header = header

    def __repr__(self) -> str:
        return f"({self.name}, {self.tcp_address})"

    def __eq__(self, other) -> bool:
        return self.tcp_address == other.tcp_address

    def close_websocket(self) -> None:
        self.websocket.close()


def instruction0(data: str, user: ServerUser) -> None:
    """Instruction 0 - set a user's name
    :param data: user's new name
    :type data: str
    :param user: user object
    :type user: ServerUser
    :return: None"""
    if not isinstance(data, str):
        raise TypeError(f"Instruction 0 - data must be str, not {type(data)}")
    user.name = data


def instruction1(data: str, user: ServerUser):
    return data


def instruction2(data: str, user: ServerUser):
    return data


DEFAULT_COMMAND_SET = [instruction0, instruction1, instruction2]
