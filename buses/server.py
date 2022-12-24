import logging

import trio
from trio_websocket import serve_websocket, WebSocketRequest, ConnectionClosed

logger = logging.getLogger("buses.server")


async def echo_server(request: WebSocketRequest):
    ws = await request.accept()
    logger.debug("Established connection: %s", ws)

    while True:
        try:
            message = await ws.get_message()
            logger.debug("Got message: %s", message)
            await ws.send_message(message)
        except ConnectionClosed:
            break


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
