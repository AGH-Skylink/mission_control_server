import threading
import time


class ServerInterruptMockup(threading.Thread):
    """A thread stopping server after certain time, for testing purposes."""

    def __init__(self, main_server):
        super().__init__()
        self.main_server = main_server

    def run(self):
        time.sleep(14)
        self.main_server.STOP_SERVER.set()

    def stop(self):
        print(f"Thread {self} stopped")
