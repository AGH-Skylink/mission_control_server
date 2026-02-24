import time
import sounddevice as sd
import socket
import numpy as np
from multiprocessing import shared_memory

udp_local_ip = "127.0.0.1"
udp_remote_ip = "127.0.0.1"
udp_local_port = 9100
udp_remote_port = 9000

samplerate = 44100
blocksize = 1024
channels = 1

"""shm_name = "wnsm_07306884"
shm_controller = ""
shm = shared_memory.SharedMemory(create=False, name=shm_name, size=24)
print(shm.name)
shm_array = np.ndarray((3,2), dtype=np.float32, buffer=shm.buf)
print(shm_array.base)
print(shm_array)
shm_array[0,0] = 2.0"""


def main():
    stream_in = sd.InputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=blocksize)
    stream_in.start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((udp_local_ip, udp_local_port))
    time.sleep(2)
    for _ in range(9000):
        data = stream_in.read(1024)[0]
        print(data)
        sock.sendto(data, (udp_remote_ip, udp_remote_port))
    while True:
        pass


if __name__ == "__main__":
    main()
