import json
import logging
from argparse import ArgumentParser
from collections import deque
from dataclasses import dataclass
from functools import wraps
from itertools import cycle, islice
from math import ceil
from random import randint, random
from typing import Callable, Awaitable, Any, Generator

import trio
from exceptiongroup import catch, ExceptionGroup
from trio_websocket import WebSocketConnection, open_websocket_url, ConnectionClosed, HandshakeError

from buses.routes import get_route, get_route_names

logger = logging.getLogger("fake_bus")


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    routes_number: int
    buses_per_route: int
    websockets_number: int
    emulator_id: str
    refresh_timeout: float
    debug: bool


def parse_config() -> Config:
    parser = ArgumentParser()
    parser.add_argument("--host", type=str, help="Server host", default="127.0.0.1")
    parser.add_argument("--port", type=int, help="Server port", default=8080)
    parser.add_argument("--routes_number", type=int, help="Number of routes on the map", default=1)
    parser.add_argument("--buses_per_route", type=int, help="Number of buses per route", default=1)
    parser.add_argument("--websockets_number", type=int, help="Number of websocket gateways", default=1)
    parser.add_argument("--emulator_id", type=str, help="Prefix for busId", default="")
    parser.add_argument("--refresh_timeout", type=float, help="Delay in updating coordinates", default=1)
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    return Config(
        args.host, args.port,
        args.routes_number, args.buses_per_route, args.websockets_number,
        args.emulator_id, args.refresh_timeout, args.debug
    )


def bus_generator(route: str, bus_id: str) -> Generator[dict[str, Any], None, None]:
    update_template = {
        "route": route,
        "busId": bus_id,
        "lat": None,
        "lng": None
    }
    coordinates = get_route(route)["coordinates"]
    shift = randint(0, len(coordinates) - 1)
    generator = islice(cycle(coordinates), shift, None)

    for latitude, longitude in generator:
        update_template["lat"] = latitude
        update_template["lng"] = longitude
        yield update_template


async def run_bus(send_channel: trio.abc.SendChannel, route: str, index: int, emulator_id: str):
    prefix = f"{emulator_id}-" if emulator_id else ""
    bus_id = f"{prefix}{route}-{index}"
    generator = bus_generator(route, bus_id)

    for message in generator:
        await send_channel.send(json.dumps(message))
        await trio.sleep(1 + random())


async def receive_updates(receive_channel: trio.abc.ReceiveChannel, buses: dict):
    async for update in receive_channel:
        message = json.loads(update)
        buses[message["busId"]] = message


async def send_updates(config: Config, buses: dict, gateway_logger: logging.Logger):
    try:
        ws: WebSocketConnection
        async with open_websocket_url(f"ws://{config.host}:{config.port}") as ws:
            gateway_logger.debug("Established connection")
            while True:
                try:
                    updates = list(buses.values())
                    message = json.dumps(updates)
                    await ws.send_message(message)
                    gateway_logger.debug("Sent update")
                    await trio.sleep(config.refresh_timeout)

                except ConnectionClosed:
                    gateway_logger.error("Connection closed")
                    raise

    except HandshakeError:
        gateway_logger.error("Connection attempt failed")
        raise


async def open_gateway(config: Config, routes: list[str], index: int):
    gateway_logger = logger.getChild(f"gateway-{index}")
    send_channel, receive_channel = trio.open_memory_channel(0)
    buses = {}
    buses_generated = 0

    async with trio.open_nursery() as nursery:
        for route in routes:
            for bus_index in range(1, config.buses_per_route + 1):
                nursery.start_soon(run_bus, send_channel, route, bus_index, config.emulator_id)
                buses_generated += 1

        gateway_logger.debug("Generated %d buses", buses_generated)
        nursery.start_soon(receive_updates, receive_channel, buses)
        nursery.start_soon(send_updates, config, buses, gateway_logger)


def relaunch_on_disconnect(func: Callable[..., Awaitable]):
    timeout = 5

    def handle(group: ExceptionGroup):
        logger.debug("Handled errors: %s", group)

    @wraps(func)
    async def wrapper(*args, **kwargs):
        while True:
            with catch({
                ConnectionClosed: handle,
                HandshakeError: handle,
            }):
                await func(*args, **kwargs)
            logger.debug("Sleeping %ds before relaunching", timeout)
            await trio.sleep(timeout)

    return wrapper


@relaunch_on_disconnect
async def imitate(config: Config, route_pairs: list[tuple[int, list[str]]]):
    async with trio.open_nursery() as nursery:
        for index, gateway_routes in route_pairs:
            nursery.start_soon(open_gateway, config, gateway_routes, index)


def main():
    config = parse_config()
    logging.basicConfig(
        format=u"%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
        level=logging.DEBUG if config.debug else logging.INFO,
        datefmt="%H:%M:%S",
    )
    logging.getLogger("trio-websocket").setLevel(logging.INFO)

    routes = deque(get_route_names(config.routes_number))
    routes_per_gateway = ceil(config.routes_number / config.websockets_number)
    route_pairs: list[tuple[int, list[str]]] = []

    for index in range(config.websockets_number):
        gateway_routes = []
        while len(gateway_routes) < routes_per_gateway and len(routes) > 0:
            gateway_routes.append(routes.popleft())
        route_pairs.append((index, gateway_routes))

    try:
        trio.run(imitate, config, route_pairs)
    except KeyboardInterrupt:
        logger.debug("Shutting down")


if __name__ == "__main__":
    main()
