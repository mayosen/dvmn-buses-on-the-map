import json
import logging

import trio
from trio_websocket import serve_websocket, WebSocketRequest, ConnectionClosed

from buses.fake_bus import run_bus
from routes import get_all_routes_names

logger = logging.getLogger("buses.server")
message_template = {
    "msgType": "Buses",
    "buses": [],
}
buses = {}


async def bus_server(request: WebSocketRequest):
    ws = await request.accept()
    server_logger = logger.getChild(f"server-{ws._id}")
    server_logger.debug("Established connection")

    while True:
        try:
            response = await ws.get_message()
            message = json.loads(response)
            buses[message["busId"]] = message
        except ConnectionClosed:
            server_logger.debug("Connection closed")
            break


async def talk_to_browser(request: WebSocketRequest):
    ws = await request.accept()
    browser_logger = logger.getChild(f"browser-{ws._id}")
    browser_logger.debug("Established connection")
    delay = 1

    while True:
        try:
            message_template["buses"] = list(buses.values())
            await ws.send_message(json.dumps(message_template))
        except ConnectionClosed:
            browser_logger.debug("Connection closed")
            break
        await trio.sleep(delay)


def parse_config():
    pass


async def main():
    logging.basicConfig(
        format=u"%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
        level=logging.DEBUG,
        datefmt="%H:%M:%S",
    )
    logging.getLogger("trio-websocket").setLevel(logging.INFO)
    host = "127.0.0.1"
    bus_port = 8080
    browser_port = 8000

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(serve_websocket, talk_to_browser, host, browser_port, None)
            nursery.start_soon(serve_websocket, bus_server, host, bus_port, None)
            await trio.sleep(0.1)
            for bus in get_all_routes_names():
                nursery.start_soon(run_bus, host, bus_port, bus, f"{bus}-0")
    except KeyboardInterrupt:
        logger.debug("Shutting down")


if __name__ == "__main__":
    trio.run(main)
