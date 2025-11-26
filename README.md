# MCPServer
The module includes class MainServer.
It could be initialized like that:

*main_server = MCPServer.MainServer("configuration_file.json")*

Next, to start the server use:

*main_server.run()*

It should be done in separate thread, so it can run simultaneously.
To give server a command while running call:

*main_server.execute_manager_command(command)*

To find the command's form check *manager_instructions*.
To find the client's requests check *client_instructions*

# Manager Instructions
- manager_instruction0: stop the server
    example: {"command": 0, "data": None}
- manager_instruction1: change downlink routing status
    example {"command": 1, "data": {"channel": 0, "user_ip": "0.0.0.0", "status": 0}},
    status: 0 - DISCONNECTED, 1 - CONNECTED, 2 - PRIORITY
- manager_instruction2: change uplink routing status
    example {"command": 1, "data": {"channel": 0, "user_ip": "0.0.0.0", "status": 0}},
    status: 0 - DISCONNECTED, 1 - CONNECTED, 2 - PRIORITY

# Client Instructions
- client_instruction0: change user's name
    example: {"command": 0, "data": "Jane Doe"}
- client_instruction1: a PTT request
    example {"command": 1, "data": {"channel": 0, "user_ip": "0.0.0.0", "status": 0}},
    "data" form could be other, it depends mostly on manager requirements
- client_instruction2: a test ping - sends back the same message
    example {"command": 2, "data": "Litwo ojczyno moja..."}