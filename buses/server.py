import logging
from argparse import ArgumentParser
from dataclasses import dataclass

import jsons
import trio
from jsons import UnfulfilledArgumentError
from trio_websocket import WebSocketRequest, WebSocketConnection, ConnectionClosed, serve_websocket

from buses.models import Bus, Message, WindowBounds, MessageType

module_logger = logging.getLogger("server")
buses: dict[str, Bus] = {}


@dataclass(frozen=True)
class Config:
    host: str
    bus_port: int
    browser_port: int
    debug: bool


def parse_config() -> Config:
    parser = ArgumentParser()
    parser.add_argument("--host", type=str, help="Server host", default="127.0.0.1")
    parser.add_argument("--bus_port", type=int, help="Buses gateway port", default=8080)
    parser.add_argument("--browser_port", type=int, help="Client browsers port", default=8000)
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    return Config(args.host, args.bus_port, args.browser_port, args.debug)


async def error_response(ws: WebSocketConnection, errors: list[str], logger: logging.Logger):
    message = Message.errors(errors)
    logger.info("Client errors: %s", errors)
    await ws.send_message(jsons.dumps(message, strict=True))


async def serve_gateway(request: WebSocketRequest):
    ws = await request.accept()
    gateway_logger = module_logger.getChild(f"gateway-{ws._id}")
    gateway_logger.info("Established connection")

    while True:
        # TODO: tests
        try:
            message = await ws.get_message()

            try:
                message = jsons.loads(message, cls=Message, strict=True)

                if message.message_type != MessageType.BUSES:
                    await error_response(ws, ["Unsupported message type"], gateway_logger)
                    continue

                bus_updates = jsons.load(message.payload, cls=list[Bus], strict=True)
                gateway_logger.debug("Got buses update")

                for bus in bus_updates:
                    buses[bus.bus_id] = bus

            except UnfulfilledArgumentError as e:
                await error_response(ws, [e.message], gateway_logger)

        except ConnectionClosed:
            gateway_logger.info("Connection closed")
            break


async def send_browser_updates(ws: WebSocketConnection, bounds: WindowBounds, logger: logging.Logger):
    delay = 1

    while True:
        if bounds.exists:
            buses_inside = list(filter(bounds.is_inside, buses.values()))
            message = Message.buses(buses_inside)
            await ws.send_message(jsons.dumps(message, strict=True))
            logger.debug("Sent update with %d buses", len(buses_inside))
        else:
            logger.debug("Bounds not exists, skipping update")

        await trio.sleep(delay)


async def listen_browser_updates(ws: WebSocketConnection, bounds: WindowBounds, logger: logging.Logger):
    # TODO: tests
    while True:
        message = await ws.get_message()

        try:
            update = jsons.loads(message, cls=Message, strict=True)

            if update.message_type != MessageType.NEW_BOUNDS:
                error = "Unsupported message type"
                await error_response(ws, [error], logger)
                continue

            bounds.update(update.payload)
            logger.debug("Got bounds update")

        except UnfulfilledArgumentError as e:
            await error_response(ws, [e.message], logger)


async def serve_browser(request: WebSocketRequest):
    ws = await request.accept()
    browser_logger = module_logger.getChild(f"browser-{ws._id}")
    browser_logger.info("Established connection")
    bounds = WindowBounds()

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(send_browser_updates, ws, bounds, browser_logger)
            nursery.start_soon(listen_browser_updates, ws, bounds, browser_logger)

    except ConnectionClosed:
        browser_logger.info("Connection closed")


async def main():
    config = parse_config()
    logging.basicConfig(
        format=u"%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
        level=logging.DEBUG if config.debug else logging.INFO,
        datefmt="%H:%M:%S",
    )
    logging.getLogger("trio-websocket").setLevel(logging.INFO)

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(serve_websocket, serve_gateway, config.host, config.bus_port, None)
            nursery.start_soon(serve_websocket, serve_browser, config.host, config.browser_port, None)

    except KeyboardInterrupt:
        module_logger.info("Shutting down")


if __name__ == "__main__":
    trio.run(main)
