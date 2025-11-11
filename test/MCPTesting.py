import threading
import time


def instruction0(data):
    return data[0] * data[1]


def instruction1(data):
    return data[0] + data[1]


def instruction2(data):
    return data


DEFAULT_COMMAND_SET = [instruction0, instruction1, instruction2]


class ServerInterruptMockup(threading.Thread):
    """A thread stopping server after certain time, for testing purposes."""

    def __init__(self, main_server):
        super().__init__()
        self.main_server = main_server

    def run(self):
        time.sleep(180)
        self.main_server.STOP_SERVER.set()

    def stop(self):
        print(f"Thread {self} stopped")
