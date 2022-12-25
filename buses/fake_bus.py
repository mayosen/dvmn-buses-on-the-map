import itertools
import json
import logging

import trio
from trio_websocket import open_websocket_url, WebSocketConnection

from buses.routes import get_route

logger = logging.getLogger("buses.fake_bus")


def bus_generator(route: str, bus_id: str):
    message_template = {
        "route": route,
        "busId": bus_id,
        "lat": None,
        "lng": None
    }
    coordinates = get_route(route)["coordinates"]
    # TODO: Использовать бесконечный генератор
    # generator = itertools.cycle(coordinates)

    for latitude, longitude in coordinates:
        message_template["lat"] = latitude
        message_template["lng"] = longitude
        yield message_template


async def bus_client(host: str, port: int, route: str, bus_id: str):
    try:
        ws: WebSocketConnection
        async with open_websocket_url(f"ws://{host}:{port}") as ws:
            logger.debug("Established connection: %s", ws)
            generator = bus_generator(route, bus_id)

            for message in generator:
                await ws.send_message(json.dumps(message))
                logger.debug("Sent message")
                await trio.sleep(1)

    except OSError as e:
        logger.error("Connection attempt failed: %s", e)
