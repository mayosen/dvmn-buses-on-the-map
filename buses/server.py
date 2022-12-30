import json
import logging

import trio
from trio_websocket import WebSocketRequest, ConnectionClosed, serve_websocket

logger = logging.getLogger("server")
message_template = {
    "msgType": "Buses",
    "buses": [],
}
buses = {}


async def receive_gateway_updates(request: WebSocketRequest):
    ws = await request.accept()
    gateway_logger = logger.getChild(f"gateway-{ws._id}")

    while True:
        try:
            response = await ws.get_message()
            message = json.loads(response)
            gateway_logger.debug("Got update")

            for update in message:
                buses[update["busId"]] = update

        except ConnectionClosed:
            gateway_logger.debug("Connection closed")
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
            browser_logger.debug("Sent update")
            await trio.sleep(delay)

        except ConnectionClosed:
            browser_logger.debug("Connection closed")
            break


def parse_config():
    # TODO
    pass


async def main():
    logging.basicConfig(
        format=u"%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
        level=logging.DEBUG,
        datefmt="%H:%M:%S",
    )
    logging.getLogger("trio-websocket").setLevel(logging.INFO)

    host = "127.0.0.1"
    browser_port = 8000
    gateway_port = 8080

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(serve_websocket, receive_gateway_updates, host, gateway_port, None)
            nursery.start_soon(serve_websocket, talk_to_browser, host, browser_port, None)

    except KeyboardInterrupt:
        logger.debug("Shutting down")


if __name__ == "__main__":
    trio.run(main)
