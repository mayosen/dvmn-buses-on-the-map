import json
import logging

import trio
from trio_websocket import serve_websocket, WebSocketRequest, ConnectionClosed
from buses.fake_bus import bus_client

logger = logging.getLogger("buses.server")

message = {
    "msgType": "Buses",
    "buses": [],
}


async def echo_server(request: WebSocketRequest):
    ws = await request.accept()
    logger.debug("Established connection: %s", ws)

    while True:
        try:
            response = await ws.get_message()
            message = json.loads(response)
            logger.debug("Got message: %s", message)
        except ConnectionClosed:
            break


def parse_config():
    pass


async def main():
    logging.basicConfig(
        format=u"%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
        level=logging.DEBUG,
        datefmt="%H:%M:%S",
    )
    logging.getLogger("trio-websocket").setLevel(logging.INFO)
    host = "127.0.0.1"
    port = 8080

    async with trio.open_nursery() as nursery:
        nursery.start_soon(serve_websocket, echo_server, host, port, None)
        # TODO: Не нужно ли поставить задержку до развертывания сервера?
        nursery.start_soon(bus_client, host, port)


if __name__ == "__main__":
    trio.run(main)
