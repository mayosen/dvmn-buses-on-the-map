import json
import logging

import trio
from trio_websocket import WebSocketRequest, WebSocketConnection, ConnectionClosed, serve_websocket

Bounds = dict[str, float]
Bus = dict[str, str | float]

logger = logging.getLogger("server")
message_template = {
    "msgType": "Buses",
    "buses": [],
}
buses: dict[str, Bus] = {}


async def serve_gateway(request: WebSocketRequest):
    ws = await request.accept()
    gateway_logger = logger.getChild(f"gateway-{ws._id}")

    while True:
        try:
            message = await ws.get_message()
            updates: list[Bus] = json.loads(message)
            gateway_logger.debug("Got update")

            for update in updates:
                buses[update["busId"]] = update

        except ConnectionClosed:
            gateway_logger.debug("Connection closed")
            break


def is_inside(bus: Bus, bounds: Bounds) -> bool:
    return (
        bounds["south_lat"] <= bus["lat"] <= bounds["north_lat"]
        and bounds["west_lng"] <= bus["lng"] <= bounds["east_lng"]
    )


async def send_browser_updates(ws: WebSocketConnection, bounds: Bounds, browser_logger: logging.Logger):
    delay = 1

    def filter_buses() -> list[Bus]:
        # Пока браузер не пришлет границы, отвечаем пустым списком
        if len(bounds) == 4:
            return list(filter(lambda bus: is_inside(bus, bounds), buses.values()))
        else:
            browser_logger.debug("No bounds, empty response")
            return []

    while True:
        buses_inside = filter_buses()
        message_template["buses"] = buses_inside
        await ws.send_message(json.dumps(message_template))
        browser_logger.debug("Sent update with %d buses", len(buses_inside))
        await trio.sleep(delay)


async def listen_browser_updates(ws: WebSocketConnection, bounds: Bounds, browser_logger: logging.Logger):
    while True:
        message = await ws.get_message()
        update = json.loads(message)
        bounds.update(update["data"])
        browser_logger.debug("Bounds updated")


async def serve_browser(request: WebSocketRequest):
    ws = await request.accept()
    browser_logger = logger.getChild(f"browser-{ws._id}")
    browser_logger.debug("Established connection")
    bounds = {}

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(send_browser_updates, ws, bounds, browser_logger)
            nursery.start_soon(listen_browser_updates, ws, bounds, browser_logger)
    except ConnectionClosed:
        browser_logger.debug("Connection closed")


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
            nursery.start_soon(serve_websocket, serve_gateway, host, gateway_port, None)
            nursery.start_soon(serve_websocket, serve_browser, host, browser_port, None)

    except KeyboardInterrupt:
        logger.debug("Shutting down")


if __name__ == "__main__":
    trio.run(main)
