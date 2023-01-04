import logging
from argparse import ArgumentParser
from dataclasses import dataclass

import jsons
import trio
from trio_websocket import WebSocketRequest, WebSocketConnection, ConnectionClosed, serve_websocket

logger = logging.getLogger("server")
buses: dict[str, "Bus"] = {}


@dataclass(frozen=True)
class Config:
    host: str
    bus_port: int
    browser_port: int
    debug: bool


def parse_config() -> Config:
    parser = ArgumentParser()
    parser.add_argument("--host", type=str, help="Server host", default="127.0.0.1")
    parser.add_argument("--bus_port", type=int, help="Buses gateway port", default=8080)
    parser.add_argument("--browser_port", type=int, help="Client browsers port", default=8000)
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    return Config(args.host, args.bus_port, args.browser_port, args.debug)


@dataclass(frozen=True)
class Bus:
    route: str
    bus_id: str
    latitude: float
    longitude: float

    @staticmethod
    def serialize(obj: "Bus", **kwargs):
        return {
            "route": obj.route,
            "busId": obj.bus_id,
            "lat": obj.latitude,
            "lng": obj.longitude,
        }

    @staticmethod
    def deserialize(obj: dict[str, str | float], cls: type, **kwargs):
        route = obj.get("route")
        bus_id = obj.get("busId")
        latitude = obj.get("lat")
        longitude = obj.get("lng")
        return Bus(route, bus_id, latitude, longitude)


@dataclass
class WindowBounds:
    south_latitude: float | None = None
    north_latitude: float | None = None
    west_longitude: float | None = None
    east_longitude: float | None = None
    exists: bool = False

    def update(self, bounds: dict):
        self.south_latitude = bounds.get("south_lat")
        self.north_latitude = bounds.get("north_lat")
        self.west_longitude = bounds.get("west_lng")
        self.east_longitude = bounds.get("east_lng")
        self.exists = True

    def is_inside(self, bus: Bus) -> bool:
        return (
            self.south_latitude <= bus.latitude <= self.north_latitude
            and self.west_longitude <= bus.longitude <= self.east_longitude
        )


async def serve_gateway(request: WebSocketRequest):
    ws = await request.accept()
    gateway_logger = logger.getChild(f"gateway-{ws._id}")
    gateway_logger.info("Established connection")

    while True:
        try:
            message = await ws.get_message()
            bus_updates = jsons.loads(message, cls=list[Bus], strict=True)
            gateway_logger.debug("Got buses update")

            for bus in bus_updates:
                buses[bus.bus_id] = bus

        except ConnectionClosed:
            gateway_logger.info("Connection closed")
            break


def format_message(buses_: list[Bus]) -> dict:
    return {
        "msgType": "Buses",
        "buses": buses_,
    }


async def send_browser_updates(ws: WebSocketConnection, bounds: WindowBounds, browser_logger: logging.Logger):
    delay = 1

    while True:
        if bounds.exists:
            buses_inside = list(filter(bounds.is_inside, buses.values()))
            message = format_message(buses_inside)
            await ws.send_message(jsons.dumps(message, strict=True))
            browser_logger.debug("Sent update with %d buses", len(buses_inside))
        else:
            browser_logger.debug("Bounds not exists, skipping update")

        await trio.sleep(delay)


async def listen_browser_updates(ws: WebSocketConnection, bounds: WindowBounds, browser_logger: logging.Logger):
    while True:
        message = await ws.get_message()
        update = jsons.loads(message)
        bounds.update(update["data"])
        browser_logger.debug("Got bounds update")


async def serve_browser(request: WebSocketRequest):
    ws = await request.accept()
    browser_logger = logger.getChild(f"browser-{ws._id}")
    browser_logger.info("Established connection")
    bounds = WindowBounds()

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(send_browser_updates, ws, bounds, browser_logger)
            nursery.start_soon(listen_browser_updates, ws, bounds, browser_logger)

    except ConnectionClosed:
        browser_logger.info("Connection closed")


async def main():
    config = parse_config()
    logging.basicConfig(
        format=u"%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
        level=logging.DEBUG if config.debug else logging.INFO,
        datefmt="%H:%M:%S",
    )
    logging.getLogger("trio-websocket").setLevel(logging.INFO)

    jsons.set_serializer(Bus.serialize, Bus)
    jsons.set_deserializer(Bus.deserialize, Bus)

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(serve_websocket, serve_gateway, config.host, config.bus_port, None)
            nursery.start_soon(serve_websocket, serve_browser, config.host, config.browser_port, None)
    except KeyboardInterrupt:
        logger.info("Shutting down")


if __name__ == "__main__":
    trio.run(main)
