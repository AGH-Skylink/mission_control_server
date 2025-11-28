from src import MCPServer
def main() -> None:
    control_panel_server = MCPServer.MainServer("src/test_config.json")
    control_panel_server.run()


if __name__ == "__main__":
    main()