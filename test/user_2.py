from websockets.sync.client import connect
import time
import sounddevice as sd


def main():
    with connect("ws://192.168.0.19:9000") as websocket:
        while True:
            audio = sd.rec(88200, samplerate=44100, channels=1, dtype='int16')
            sd.wait()
            message = audio.tobytes()
            websocket.send(message)
            print("Sound sent")
            time.sleep(5)
            message = websocket.recv()
            print(message)
            time.sleep(1)


if __name__ == "__main__":
    main()
