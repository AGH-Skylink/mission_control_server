from websockets.sync.client import connect
import time
import json


def main():
    with connect("ws://localhost:9000") as websocket:
        while True:
            message = {"command": 0, "data": [2,3]}
            message_json = json.dumps(message)
            websocket.send(message_json)
            time.sleep(1)
            message_json = websocket.recv()
            message = json.loads(message_json)
            print(message)
            time.sleep(1)


if __name__ == "__main__":
    main()
