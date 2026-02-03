from websockets.sync.client import connect
import time
import sounddevice as sd
import socket

udp_local_ip = "127.0.0.1"
udp_remote_ip = "127.0.0.1"
udp_local_port = 9101
udp_remote_port = 9000

samplerate = 44100
blocksize = 1024
channels = 1


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
from websockets.sync.client import connect
import time
import json


def main():
    with connect("ws://localhost:9000") as websocket:
        while True:
            message = {"command": 1, "data": [4,5]}
            message_json = json.dumps(message)
            websocket.send(message_json)
            time.sleep(1)
            message_json = websocket.recv()
            message = json.loads(message_json)
            print(message)
            time.sleep(1)


if __name__ == "__main__":
    main()
