import logging
from argparse import ArgumentParser
from dataclasses import dataclass
from functools import partial
from typing import Callable, Awaitable

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
    refresh_timeout: float
    debug: bool

    @classmethod
    def parse(cls) -> "Config":
        parser = ArgumentParser()
        parser.add_argument("--host", type=str, help="Server host", default="127.0.0.1")
        parser.add_argument("--bus_port", type=int, help="Buses gateway port", default=8080)
        parser.add_argument("--browser_port", type=int, help="Client browsers port", default=8000)
        parser.add_argument("--refresh_timeout", type=float, help="Delay between coordinates updates", default=1)
        parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
        args = parser.parse_args()

        return cls(args.host, args.bus_port, args.browser_port, args.refresh_timeout, args.debug)


def error_response_builder(ws: WebSocketConnection, logger: logging.Logger) -> Callable[[list[str]], Awaitable]:
    async def error_response(errors: list[str]):
        message = Message.errors(errors)
        logger.info("Client errors: %s", errors)
        await ws.send_message(jsons.dumps(message, strict=True))

    return error_response


async def serve_gateway(request: WebSocketRequest):
    ws = await request.accept()
    logger = module_logger.getChild(f"gateway-{ws._id}")
    logger.info("Established connection")
    error_response = error_response_builder(ws, logger)

    while True:
        # TODO: tests
        try:
            message = await ws.get_message()

            try:
                message = jsons.loads(message, cls=Message, strict=True)

                if message.msg_type != MessageType.BUSES:
                    await error_response(["Unsupported message type"])
                    continue

                bus_updates = jsons.load(message.payload, cls=list[Bus], strict=True)
                logger.debug("Got buses update")

                for bus in bus_updates:
                    buses[bus.bus_id] = bus

            except UnfulfilledArgumentError as e:
                await error_response([e.message])

        except ConnectionClosed:
            logger.info("Connection closed")
            break


async def send_browser_updates(ws: WebSocketConnection, bounds: WindowBounds, timeout: float, logger: logging.Logger):
    while True:
        if bounds.exists:
            buses_inside = list(filter(bounds.is_inside, buses.values()))
            message = Message.buses(buses_inside)
            await ws.send_message(jsons.dumps(message, strict=True))
            logger.debug("Sent update with %d buses", len(buses_inside))
        else:
            logger.debug("Bounds not exists, skipping update")

        await trio.sleep(timeout)


async def listen_browser_updates(ws: WebSocketConnection, bounds: WindowBounds, logger: logging.Logger):
    # TODO: tests
    error_response = error_response_builder(ws, logger)

    while True:
        message = await ws.get_message()

        try:
            update = jsons.loads(message, cls=Message, strict=True)

            if update.msg_type != MessageType.NEW_BOUNDS:
                await error_response(["Unsupported message type"])
                continue

            bounds.update(update.payload)
            logger.debug("Got bounds update")

        except UnfulfilledArgumentError as e:
            await error_response([e.message])


async def serve_browser(request: WebSocketRequest, timeout: float):
    ws = await request.accept()
    logger = module_logger.getChild(f"browser-{ws._id}")
    logger.info("Established connection")
    bounds = WindowBounds()

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(send_browser_updates, ws, bounds, timeout, logger)
            nursery.start_soon(listen_browser_updates, ws, bounds, logger)

    except ConnectionClosed:
        logger.info("Connection closed")


async def main():
    config = Config.parse()
    logging.basicConfig(
        format=u"%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
        level=logging.DEBUG if config.debug else logging.INFO,
        datefmt="%H:%M:%S",
    )
    logging.getLogger("trio-websocket").setLevel(logging.INFO)
    module_logger.debug(config)

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(serve_websocket, serve_gateway, config.host, config.bus_port, None)
            nursery.start_soon(
                serve_websocket,
                partial(serve_browser, timeout=config.refresh_timeout), config.host, config.browser_port, None
            )

    except KeyboardInterrupt:
        module_logger.info("Shutting down")


if __name__ == "__main__":
    trio.run(main)
