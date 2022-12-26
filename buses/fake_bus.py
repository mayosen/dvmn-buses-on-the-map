import json
import logging
from itertools import cycle, islice
from random import randint

import trio

from buses.routes import get_route
from buses.utils import generate_id

logger = logging.getLogger("buses.fake_bus")


def _bus_generator(route: str, bus_id: str):
    message_template = {
        "route": route,
        "busId": bus_id,
        "lat": None,
        "lng": None
    }
    coordinates = get_route(route)["coordinates"]
    skip = randint(0, len(coordinates) - 1)
    generator = islice(cycle(coordinates), skip, None)
    # TODO: Сделать равномерное распределение автобусов на маршруте?

    for latitude, longitude in generator:
        message_template["lat"] = latitude
        message_template["lng"] = longitude
        yield message_template


def _generate_bus_id(route: str, index: int):
    return f"{route}:{index}"


async def run_bus(send_channel: trio.MemorySendChannel, route: str, index: int):
    bus_id = _generate_bus_id(route, index)
    # logger.debug("Bus %s bound to send channel %s", bus_id, generate_id(send_channel))
    generator = _bus_generator(route, bus_id)
    delay = 1

    for message in generator:
        await send_channel.send(json.dumps(message))
        await trio.sleep(delay)
