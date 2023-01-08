import logging
from functools import partial

import jsons
import pytest
from trio_websocket import open_websocket_url, serve_websocket

from buses.server import serve_browser, serve_gateway

HOST = "127.0.0.1"
BROWSER_PORT = 8000
GATEWAY_PORT = 8080


@pytest.fixture(scope="session", autouse=True)
def setup_logging_level():
    logging.getLogger("trio-websocket").setLevel(logging.INFO)


@pytest.fixture
async def browser(nursery):
    server = await nursery.start(serve_websocket, partial(serve_browser, timeout=1), HOST, BROWSER_PORT, None)
    async with open_websocket_url(f"ws://{HOST}:{BROWSER_PORT}") as ws:
        yield ws


@pytest.fixture
async def gateway(nursery):
    server = await nursery.start(serve_websocket, serve_gateway, HOST, GATEWAY_PORT, None)
    async with open_websocket_url(f"ws://{HOST}:{GATEWAY_PORT}") as ws:
        yield ws


async def exchange(ws, message):
    await ws.send_message(jsons.dumps(message))
    return jsons.loads(await ws.get_message())


class TestBrowser:
    async def test_no_message_type(self, browser):
        message = {}
        message = await exchange(browser, message)
        assert message["msgType"] == "Errors"
        assert "msgType" in message["errors"][0]

    async def test_incorrect_message_type(self, browser):
        message = {
            "msgType": "INCORRECT"
        }
        message = await exchange(browser, message)
        assert message["msgType"] == "Errors"
        assert "INCORRECT" in message["errors"][0]

    async def test_no_payload(self, browser):
        message = {
            "msgType": "NewBounds"
        }
        message = await exchange(browser, message)
        assert message["msgType"] == "Errors"
        error = message["errors"][0].lower()
        assert "payload" in error and "data" in error

    async def test_incorrect_payload_name(self, browser):
        message = {
            "msgType": "NewBounds",
            "payload": []
        }
        message = await exchange(browser, message)
        assert message["msgType"] == "Errors"
        error = message["errors"][0].lower()
        assert "payload" in error and "data" in error

    async def test_incorrect_payload_type(self, browser):
        message = {
            "msgType": "NewBounds",
            "data": None
        }
        message = await exchange(browser, message)
        assert message["msgType"] == "Errors"
        assert "dict" in message["errors"][0]

    async def test_incorrect_bounds_body(self, browser):
        message = {
            "msgType": "NewBounds",
            "data": {
                1: 37.65563964843751,
                2: 55.77367652953477,
            },
        }
        message = await exchange(browser, message)
        assert message["msgType"] == "Errors"
        error = message["errors"][0].lower()
        assert "field" in error


class TestGateway:
    async def test_no_message_type(self, gateway):
        message = {}
        message = await exchange(gateway, message)
        assert message["msgType"] == "Errors"
        assert "msgType" in message["errors"][0]

    async def test_incorrect_message_type(self, gateway):
        message = {
            "msgType": "INCORRECT"
        }
        message = await exchange(gateway, message)
        assert message["msgType"] == "Errors"
        assert "INCORRECT" in message["errors"][0]

    async def test_no_payload(self, gateway):
        message = {
            "msgType": "Buses"
        }
        message = await exchange(gateway, message)
        assert message["msgType"] == "Errors"
        error = message["errors"][0].lower()
        assert "payload" in error and "buses" in error

    async def test_incorrect_payload_name(self, gateway):
        message = {
            "msgType": "Buses",
            "payload": []
        }
        message = await exchange(gateway, message)
        assert message["msgType"] == "Errors"
        error = message["errors"][0].lower()
        assert "payload" in error and "buses" in error

    async def test_incorrect_payload_type(self, gateway):
        message = {
            "msgType": "Buses",
            "buses": None
        }
        message = await exchange(gateway, message)
        assert message["msgType"] == "Errors"
        assert "list" in message["errors"][0]

    async def test_incorrect_bus_body(self, gateway):
        message = {
            "msgType": "Buses",
            "buses": [
                {
                    "busId": "ID",
                    "route__": None
                }
            ]
        }
        message = await exchange(gateway, message)
        assert message["msgType"] == "Errors"
        assert "route" in message["errors"][0]
