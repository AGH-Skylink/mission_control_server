import socket
import numpy as np
import sounddevice as sd

UDP_IP = "127.0.0.1"
UDP_PORT = 9103
BLOCKSIZE = 1024
CHANNELS = 1
SAMPLERATE = 44100

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

# stream do odtwarzania
stream_out = sd.OutputStream(samplerate=SAMPLERATE, channels=CHANNELS, dtype='float32', blocksize=BLOCKSIZE)
stream_out.start()

while True:
    data, addr = sock.recvfrom(4096)
    print(data, addr)# odbiór datagramu
    audio_block = np.frombuffer(data, dtype=np.float32)  # konwersja na ndarray
    stream_out.write(audio_block)
    print("XD")# odtwarzanie