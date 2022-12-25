import itertools
import json
import logging

import trio
from trio_websocket import open_websocket_url, WebSocketConnection

from buses.routes import get_route

logger = logging.getLogger("buses.fake_bus")


def _generator(route: str, bus_id: str):
    message_template = {
        "route": route,
        "busId": bus_id,
        "lat": None,
        "lng": None
    }
    coordinates = get_route(route)["coordinates"]
    generator = itertools.cycle(coordinates)

    for latitude, longitude in generator:
        message_template["lat"] = latitude
        message_template["lng"] = longitude
        yield message_template


async def run_bus(host: str, port: int, route: str, bus_id: str):
    bus_logger = logger.getChild(f"bus-{bus_id}")
    delay = 1

    try:
        ws: WebSocketConnection
        async with open_websocket_url(f"ws://{host}:{port}") as ws:
            bus_logger.debug("Established connection")
            generator = _generator(route, bus_id)

            for message in generator:
                await ws.send_message(json.dumps(message))
                await trio.sleep(delay)

    except OSError as e:
        bus_logger.error("Connection attempt failed: %s", e)
