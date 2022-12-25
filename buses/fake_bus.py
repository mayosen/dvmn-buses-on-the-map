import json
import logging
from itertools import cycle, islice
from random import randint

import trio
from trio_websocket import open_websocket_url, WebSocketConnection

from buses.routes import get_route

logger = logging.getLogger("buses.fake_bus")


def _generate_bus_id(route: str, index: int):
    return f"{route}:{index}"


def _bus_generator(route: str, bus_id: str):
    message_template = {
        "route": route,
        "busId": bus_id,
        "lat": None,
        "lng": None
    }
    coordinates = get_route(route)["coordinates"]
    skip = randint(1, len(coordinates))
    generator = islice(cycle(coordinates), skip, None)

    for latitude, longitude in generator:
        message_template["lat"] = latitude
        message_template["lng"] = longitude
        yield message_template


async def run_bus(host: str, port: int, route: str, index: int):
    bus_id = _generate_bus_id(route, index)
    bus_logger = logger.getChild(f"bus-{bus_id}")
    delay = 1

    try:
        ws: WebSocketConnection
        async with open_websocket_url(f"ws://{host}:{port}") as ws:
            bus_logger.debug("Established connection")
            generator = _bus_generator(route, bus_id)

            for message in generator:
                await ws.send_message(json.dumps(message))
                await trio.sleep(delay)

    except OSError as e:
        bus_logger.error("Connection attempt failed: %s", e)
