from websockets.sync.client import connect
import time
import json


def main():
    with connect("ws://localhost:9000") as websocket:
        while True:
            message = {"command": 1, "data": "user_0"}
            message_json = json.dumps(message)
            websocket.send(message_json)
            time.sleep(1)
            message_json = websocket.recv()
            message2 = json.loads(message_json)
            print(message2)
            time.sleep(1)


if __name__ == "__main__":
    main()
