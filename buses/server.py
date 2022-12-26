import json
import logging
from random import randint, choice

import trio
from trio_websocket import serve_websocket, WebSocketRequest, ConnectionClosed

from buses.fake_bus import run_bus
from buses.utils import generate_id
from routes import get_all_route_names

logger = logging.getLogger("buses.server")
message_template = {
    "msgType": "Buses",
    "buses": [],
}
buses = {}


async def receive_updates(receive_channel: trio.MemoryReceiveChannel):
    channel_logger = logger.getChild(f"channel-{generate_id(receive_channel)}")

    async for update in receive_channel:
        # channel_logger.debug("Received update")
        message = json.loads(update)
        buses[message["busId"]] = message


async def talk_to_browser(request: WebSocketRequest):
    ws = await request.accept()
    browser_logger = logger.getChild(f"connect-{ws._id}")
    browser_logger.debug("Established connection")
    delay = 1

    while True:
        try:
            message_template["buses"] = list(buses.values())
            await ws.send_message(json.dumps(message_template))
            browser_logger.debug("Sent update")
        except ConnectionClosed:
            browser_logger.debug("Connection closed")
            break
        await trio.sleep(delay)


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
    channels = 5

    try:
        async with trio.open_nursery() as nursery:
            send_channels = []

            for _ in range(channels):
                send_channel, receive_channel = trio.open_memory_channel(0)
                send_channels.append(send_channel)
                nursery.start_soon(receive_updates, receive_channel)

            nursery.start_soon(serve_websocket, talk_to_browser, host, browser_port, None)
            buses_generated = 0

            for route in get_all_route_names():
                # buses_on_route = randint(1, 100)
                buses_on_route = 33
                # logger.debug("Generating %d buses on route %s", buses_on_route, route)

                for index in range(1, buses_on_route + 1):
                    buses_generated += 1
                    nursery.start_soon(run_bus, choice(send_channels), route, index)

            logger.debug("Totally generated %d buses", buses_generated)

    except KeyboardInterrupt:
        logger.debug("Shutting down")


if __name__ == "__main__":
    trio.run(main)
