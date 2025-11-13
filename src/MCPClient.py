import websockets
from websockets.sync.server import serve
import json
import numpy as np
import sounddevice as sd
import socket


class ServerUser:
    def __init__(self, ip_addr: str, port: int, server_id: int| None = None, name: str | None = None):
        self.name = name
        if len(ip_addr) < 10 or ip_addr[:10] != "192.168.0.":
            raise ValueError(f"Invalid IP address - {ip_addr}")
        self.connection_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.connection_socket.bind((ip_addr, port))
        self.server_id = server_id

    def __repr__(self) -> str:
        return f"({self.name}, {self.connection_socket.getsockname()})"

    def __eq__(self, other) -> bool:
        return self.connection_socket.getsockname() == other.connection_socket.getsockname()

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