import socket
import numpy as np
import threading
import sounddevice as sd
from core.logger import monitor
import json
import os
from pathlib import Path

def load_tablet_identity(file_name="tablet_config.json"):
    config_path = Path(__file__).parent / file_name
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"tablet_name": f"UNKNOWN_TAB_{os.getpid()}", "server_ip": "127.0.0.1"}

tablet_cfg = load_tablet_identity()
MY_NAME = tablet_cfg.get("tablet_name", "DEFAULT_TAB")

class MCPTabletClient:
    """
    Operator Tablet Client Logic.
    Handles UDP Audio streams and PTT signaling.
    """
    def __init__(self, config):
        self.server_addr = (config["server_ip"], config["audio_port"])
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.is_streaming = False
        self.chunk_size = 1024
        monitor.log_event("CLIENT_INIT", {"name": config["tablet_name"]}, message="Client initialized from config")

    def _audio_callback(self, indata, outdata, frames, time, status):
        """Standard full-duplex callback for sounddevice"""
        if self.is_streaming:
            self.udp_sock.sendto(indata.astype(np.float32).tobytes(), self.server_addr)

        # In a real scenario, incoming UDP audio would be queued here for playback
        # For now, this is a placeholder for output processing
        pass

    def start_ptt(self):
        self.is_streaming = True
        print("PTT ACTIVE: Streaming audio...")
        monitor.log_event("PTT_PRESSED", message="User started transmission")

    def stop_ptt(self):
        self.is_streaming = False
        print("PTT IDLE.")
        monitor.log_event("PTT_RELEASED", message="User stopped transmission")

    def run_audio_engine(self):
        with sd.Stream(samplerate=44100, blocksize=self.chunk_size,
                       dtype='float32', channels=1, callback=self._audio_callback):
            print("Tablet Audio Engine Online.")
            threading.Event().wait()

client = MCPTabletClient(tablet_cfg)