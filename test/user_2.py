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
        time.sleep(2)
        for _ in range(9000):
            data = stream_in.read(1024, exception_on_overflow=False)
            sock.sendto(data, (udp_remote_ip, udp_remote_port))
        while True:
            pass


if __name__ == "__main__":
    main()
