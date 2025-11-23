from websockets.sync.client import connect
import time
import sounddevice as sd
import pyaudio
import socket

tcp_remote_address = "ws://localhost:9000"
udp_local_ip = "127.0.0.1"
udp_remote_ip = "127.0.0.1"
udp_local_port = 9001
udp_remote_port = 9000

def main():
    with connect(tcp_remote_address) as websocket:
        audio = pyaudio.PyAudio()
        stream_in = audio.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((udp_local_ip, udp_local_port))
        header = bytes()
        time.sleep(2)
        print(udp_local_ip.split("."))
        for num in [int(x) for x in udp_local_ip.split(".")]:
            header += num.to_bytes(1, byteorder='little')
        print()
        for _ in range(9000):
            data = stream_in.read(1024, exception_on_overflow=False)
            sock.sendto(header + data, (udp_remote_ip, udp_remote_port))
        while True:
            pass


if __name__ == "__main__":
    main()
