import json
import logging

import trio
from trio_websocket import serve_websocket, WebSocketRequest, ConnectionClosed
from routes import ROUTES

logger = logging.getLogger("buses.server")

bus = {
    "busId": "а982ан", "lat": None, "lng": None, "route": "156"
}

message = {
    "msgType": "Buses",
    "buses": [bus],
}


async def echo_server(request: WebSocketRequest):
    ws = await request.accept()
    logger.debug("Established connection: %s", ws)
    route: dict = ROUTES.get("156")

    for coordinates in route["coordinates"]:
        try:
            bus["lat"] = coordinates[0]
            bus["lng"] = coordinates[1]
            payload = json.dumps(message)
            logger.debug("Sending payload: %s", payload)
            await ws.send_message(payload)
        except ConnectionClosed:
            break
        await trio.sleep(0.1)


def parse_config():
    pass


async def main():
    logging.basicConfig(
        format=u"%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        level=logging.DEBUG,
        datefmt="%H:%M:%S",
    )
    logging.getLogger("trio-websocket").setLevel(logging.INFO)

    await serve_websocket(echo_server, "127.0.0.1", 8000, ssl_context=None)


if __name__ == "__main__":
    trio.run(main)
