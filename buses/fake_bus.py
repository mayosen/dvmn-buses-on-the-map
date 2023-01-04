import logging
from argparse import ArgumentParser
from collections import deque
from dataclasses import dataclass
from functools import wraps
from itertools import cycle, islice
from math import ceil
from random import randint, random
from typing import Callable, Awaitable, Generator, Union

import jsons
import trio
from exceptiongroup import ExceptionGroup, catch
from trio_websocket import WebSocketConnection, ConnectionClosed, HandshakeError, open_websocket_url

from buses.routes import get_route, get_route_names

GatewayRoutes = tuple[int, list[str]]
Update = dict[str, Union[str, float]]
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


def bus_generator(route: str, bus_id: str) -> Generator[Update, None, None]:
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


async def run_bus(send_channel: trio.abc.SendChannel[Update], route: str, index: int, emulator_id: str):
    prefix = f"{emulator_id}-" if emulator_id else ""
    bus_id = f"{prefix}{route}-{index}"
    generator = bus_generator(route, bus_id)

    for update in generator:
        await send_channel.send(update)
        await trio.sleep(1 + random())


async def receive_updates(receive_channel: trio.abc.ReceiveChannel[Update], buses: dict):
    async for update in receive_channel:
        buses[update["busId"]] = update


async def send_updates(config: Config, buses: dict, gateway_logger: logging.Logger):
    try:
        ws: WebSocketConnection
        async with open_websocket_url(f"ws://{config.host}:{config.port}") as ws:
            gateway_logger.info("Established connection")

            while True:
                try:
                    updates = list(buses.values())
                    await ws.send_message(jsons.dumps(updates))
                    gateway_logger.debug("Sent update")
                    await trio.sleep(config.refresh_timeout)

                except ConnectionClosed:
                    gateway_logger.info("Connection closed")
                    raise

    except HandshakeError:
        gateway_logger.info("Connection attempt failed")
        raise


async def open_gateway(config: Config, index: int, routes: list[str]):
    gateway_logger = logger.getChild(f"gateway-{index}")
    send_channel, receive_channel = trio.open_memory_channel(0)
    buses = {}
    buses_generated = 0

    async with trio.open_nursery() as nursery:
        for route in routes:
            for bus_index in range(1, config.buses_per_route + 1):
                nursery.start_soon(run_bus, send_channel, route, bus_index, config.emulator_id)
                buses_generated += 1

        gateway_logger.info("Generated %d buses", buses_generated)
        nursery.start_soon(receive_updates, receive_channel, buses)
        nursery.start_soon(send_updates, config, buses, gateway_logger)


def relaunch_on_disconnect(func: Callable[..., Awaitable]):
    timeout = 5

    def handle(group: ExceptionGroup):
        logger.info("Handled errors: %s", group)

    @wraps(func)
    async def wrapper(*args, **kwargs):
        while True:
            with catch({
                ConnectionClosed: handle,
                HandshakeError: handle,
            }):
                await func(*args, **kwargs)
            logger.info("Sleeping %ds before relaunching", timeout)
            await trio.sleep(timeout)

    return wrapper


@relaunch_on_disconnect
async def imitate(config: Config, gateway_routes: list[GatewayRoutes]):
    async with trio.open_nursery() as nursery:
        for index, routes in gateway_routes:
            nursery.start_soon(open_gateway, config, index, routes)


def distribute_routes(routes_number: int, websockets_number: int) -> list[GatewayRoutes]:
    route_names = deque(get_route_names(routes_number))
    routes_per_gateway = ceil(routes_number / websockets_number)
    gateway_routes: list[GatewayRoutes] = []

    for index in range(websockets_number):
        routes = []
        while len(routes) < routes_per_gateway and len(route_names) > 0:
            routes.append(route_names.popleft())
        gateway_routes.append((index, routes))

    return gateway_routes


async def main():
    config = parse_config()
    logging.basicConfig(
        format=u"%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
        level=logging.DEBUG if config.debug else logging.INFO,
        datefmt="%H:%M:%S",
    )
    logging.getLogger("trio-websocket").setLevel(logging.INFO)

    gateway_routes = distribute_routes(config.routes_number, config.websockets_number)

    try:
        await imitate(config, gateway_routes)
    except KeyboardInterrupt:
        logger.info("Shutting down")


if __name__ == "__main__":
    trio.run(main)
