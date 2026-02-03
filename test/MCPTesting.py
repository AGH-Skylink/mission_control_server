# TO DELETE
import threading
import time
import sounddevice as sd
from queue import Queue

samplerate = 44100
blocksize = 1024
channels = 1


class AudioPlayer(threading.Thread):
    """A thread playing an audio, for testing purposes."""

    def __init__(self, main_server):
        self.is_active = True
        self.main_server = main_server
        super().__init__()

    def run(self):
        stream_in = sd.InputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=blocksize)
        stream_out = sd.OutputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=blocksize)
        stream_in.start()
        stream_out.start()
        buuuuf0 = Queue(maxsize=10)
        buuuuf1 = Queue(maxsize=10)
        # time.sleep(10)
        while self.is_active:
            """if not self.main_server.received_audio_buffers[0].empty():
                data = self.main_server.received_audio_buffers[0].get_nowait()
                stream_out.write(data)"""
            """if not self.main_server.received_audio_buffers[0].empty():
                data = self.main_server.received_audio_buffers[0].get_nowait()
                # print(self.main_server.received_audio_buffers[0].qsize())
                self.main_server.transmitted_audio_buffers[0].put_nowait(data)"""
            if not self.main_server.received_audio_buffers[0].empty():
                data = self.main_server.received_audio_buffers[0].get_nowait()
                # print(self.main_server.received_audio_buffers[0].qsize())
                buuuuf0.put(data)
            if not buuuuf0.empty():
                data = buuuuf0.get_nowait()
                self.main_server.transmitted_audio_buffers[1].put(data)
                print("test")
            if not self.main_server.received_audio_buffers[1].empty():
                data = self.main_server.received_audio_buffers[1].get_nowait()
                # print(self.main_server.received_audio_buffers[0].qsize())
                buuuuf1.put(data)
            if not buuuuf1.empty():
                data = buuuuf1.get_nowait()
                self.main_server.transmitted_audio_buffers[0].put(data)
                print("test")
            """data = stream_in.read(1024, exception_on_overflow=False)
            if self.main_server.active_users[0] is not None:
                self.main_server.transmitted_audio_buffers[0].put_nowait(data)"""

    def stop(self):
        self.is_active = False
        print(f"Thread {self} stopped")


class ServerInterruptMockup(threading.Thread):
    """A thread stopping server after certain time, for testing purposes."""

    def __init__(self, main_server):
        super().__init__()
        self.main_server = main_server

    def run(self):
        time.sleep(18)
        self.main_server.manager_command_buffer.put({"command": 0, "data": {}})

    def stop(self):
        print(f"Thread {self} stopped")
