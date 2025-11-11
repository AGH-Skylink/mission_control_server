import websockets
from websockets.sync.server import serve
import json
import numpy as np
import sounddevice as sd
from test.MCPTesting import DEFAULT_COMMAND_SET


class ServerUser:
    def __init__(self, iden: int| None = None, name: str | None = None):
        self.id = iden
        self.name = name

