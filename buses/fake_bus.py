import logging
from argparse import ArgumentParser
from collections import deque
from dataclasses import dataclass
from functools import wraps
from itertools import islice
from math import ceil
from random import randint, random
from typing import Callable, Awaitable, Iterable, Any, Collection, Generator

import jsons
import trio
from exceptiongroup import ExceptionGroup, catch
from trio_websocket import WebSocketConnection, ConnectionClosed, HandshakeError, open_websocket_url

from buses.models import Bus, Message
from buses.routes import get_route_names, read_route

module_logger = logging.getLogger("fake_bus")


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

    @classmethod
    def parse(cls) -> "Config":
        parser = ArgumentParser()
        parser.add_argument("--host", type=str, help="Server host", default="127.0.0.1")
        parser.add_argument("--port", type=int, help="Server port", default=8080)
        parser.add_argument("--routes_number", type=int, help="Number of routes on the map", default=1)
        parser.add_argument("--buses_per_route", type=int, help="Number of buses per route", default=1)
        parser.add_argument("--websockets_number", type=int, help="Number of websocket gateways", default=1)
        parser.add_argument("--emulator_id", type=str, help="Prefix for busId", default="")
        parser.add_argument("--refresh_timeout", type=float, help="Delay between coordinates updates", default=1)
        parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
        args = parser.parse_args()

        return cls(
            args.host, args.port,
            args.routes_number, args.buses_per_route, args.websockets_number,
            args.emulator_id, args.refresh_timeout, args.debug
        )


class FakeBus(Bus):
    def __init__(self, route: str, bus_id: str, generator: Iterable[tuple[float, float]]):
        super().__init__(route, bus_id)
        self.generator = iter(generator)
        self.move()

    def move(self):
        latitude, longitude = next(self.generator)
        self.latitude = latitude
        self.longitude = longitude

    async def run(self):
        while True:
            self.move()
            await trio.sleep(1.5 + random() / 10)


def cycle(sequence: Collection[Any]) -> Iterable[Any]:
    """Цикл без копирования элементов исходной последовательности."""

    while True:
        for item in sequence:
            yield item


def coordinates_generator(coordinates: list[tuple[float, float]], shift: int) -> Iterable[tuple[float, float]]:
    return islice(cycle(coordinates), shift, None)


def distribute_routes(routes_number: int, websockets_number: int) -> Generator[list[str], None, None]:
    """Распределение маршрутов между шлюзами."""

    routes = deque(get_route_names(routes_number))
    routes_per_gateway = ceil(routes_number / websockets_number)

    for _ in range(websockets_number):
        gateway_routes = []
        while len(gateway_routes) < routes_per_gateway and len(routes) > 0:
            gateway_routes.append(routes.popleft())
        yield gateway_routes


def generate_bus_id(emulator_id: str, route: str, index: int) -> str:
    prefix = f"{emulator_id}-" if emulator_id else ""
    return f"{prefix}{route}-{index}"


def distribute_buses(config: Config) -> list[tuple[logging.Logger, list[FakeBus]]]:
    """Распределение автобусов между шлюзами."""

    routes_generator = distribute_routes(config.routes_number, config.websockets_number)
    gateway_buses = []

    for gateway_index, routes in enumerate(routes_generator):
        logger = module_logger.getChild(f"gateway-{gateway_index}")
        buses = []

        for route in routes:
            coordinates = read_route(route)["coordinates"]
            interval = ceil(len(coordinates) / config.buses_per_route)

            for bus_index in range(config.buses_per_route):
                bus_id = generate_bus_id(config.emulator_id, route, bus_index)
                shift = interval * bus_index + randint(0, 2)
                buses.append(FakeBus(route, bus_id, coordinates_generator(coordinates, shift)))

        logger.debug("Generated %d buses", len(buses))
        gateway_buses.append((logger, buses))

    return gateway_buses


async def send_updates(config: Config, buses: list[Bus], logger: logging.Logger):
    try:
        ws: WebSocketConnection
        async with open_websocket_url(f"ws://{config.host}:{config.port}") as ws:
            logger.info("Established connection")
            sleep = 2 * random()
            logger.debug("Sleeping for %.2fs", sleep)
            await trio.sleep(sleep)

            while True:
                try:
                    message = Message.buses(buses)
                    await ws.send_message(jsons.dumps(message, strict=True))
                    logger.debug("Sent update")
                    await trio.sleep(config.refresh_timeout)

                except ConnectionClosed:
                    logger.info("Connection closed")
                    raise

    except HandshakeError:
        logger.info("Connection attempt failed")
        raise


async def open_gateway(config: Config, logger: logging.Logger, buses: list[FakeBus]):
    async with trio.open_nursery() as nursery:
        for bus in buses:
            nursery.start_soon(bus.run)

        nursery.start_soon(send_updates, config, buses, logger)


def relaunch_on_disconnect(func: Callable[..., Awaitable]):
    timeout = 5

    def handle(group: ExceptionGroup):
        module_logger.info("Handled errors: %s", group)

    @wraps(func)
    async def wrapper(*args, **kwargs):
        while True:
            with catch({
                ConnectionClosed: handle,
                HandshakeError: handle,
            }):
                await func(*args, **kwargs)
            module_logger.info("Sleeping %ds before relaunch attempt", timeout)
            await trio.sleep(timeout)

    return wrapper


@relaunch_on_disconnect
async def imitate(config: Config, gateway_buses):
    async with trio.open_nursery() as nursery:
        for logger, buses in gateway_buses:
            nursery.start_soon(open_gateway, config, logger, buses)


async def main():
    config = Config.parse()
    logging.basicConfig(
        format=u"%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
        level=logging.DEBUG if config.debug else logging.INFO,
        datefmt="%H:%M:%S",
    )
    logging.getLogger("trio-websocket").setLevel(logging.INFO)
    module_logger.debug(config)

    gateway_buses = distribute_buses(config)

    try:
        await imitate(config, gateway_buses)
    except KeyboardInterrupt:
        module_logger.info("Shutting down")


if __name__ == "__main__":
    trio.run(main)
