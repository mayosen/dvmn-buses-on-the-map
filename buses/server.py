from dataclasses import dataclass

import jsons
import logging

import trio
from trio_websocket import WebSocketRequest, WebSocketConnection, ConnectionClosed, serve_websocket

logger = logging.getLogger("server")
message_template = {
    "msgType": "Buses",
    "buses": [],
}
buses: dict[str, "Bus"] = {}


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

    while True:
        try:
            message = await ws.get_message()
            bus_updates = jsons.loads(message, cls=list[Bus], strict=True)
            gateway_logger.debug("Got update buses")

            for bus in bus_updates:
                buses[bus.bus_id] = bus

        except ConnectionClosed:
            gateway_logger.debug("Connection closed")
            break


async def send_browser_updates(ws: WebSocketConnection, bounds: WindowBounds, browser_logger: logging.Logger):
    delay = 1

    while True:
        if bounds.exists:
            buses_inside = list(filter(bounds.is_inside, buses.values()))
            message_template["buses"] = buses_inside
            await ws.send_message(jsons.dumps(message_template, strict=True))
            browser_logger.debug("Sent update with %d buses", len(buses_inside))
        else:
            browser_logger.debug("Bounds not exists, skipping update")

        await trio.sleep(delay)


async def listen_browser_updates(ws: WebSocketConnection, bounds: WindowBounds, browser_logger: logging.Logger):
    while True:
        message = await ws.get_message()
        update = jsons.loads(message)
        bounds.update(update["data"])
        browser_logger.debug("Bounds updated")


async def serve_browser(request: WebSocketRequest):
    ws = await request.accept()
    browser_logger = logger.getChild(f"browser-{ws._id}")
    browser_logger.debug("Established connection")
    bounds = WindowBounds()

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(send_browser_updates, ws, bounds, browser_logger)
            nursery.start_soon(listen_browser_updates, ws, bounds, browser_logger)

    except ConnectionClosed:
        browser_logger.debug("Connection closed")


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

    jsons.set_serializer(Bus.serialize, Bus)
    jsons.set_deserializer(Bus.deserialize, Bus)

    host = "127.0.0.1"
    browser_port = 8000
    gateway_port = 8080

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(serve_websocket, serve_gateway, host, gateway_port, None)
            nursery.start_soon(serve_websocket, serve_browser, host, browser_port, None)

    except KeyboardInterrupt:
        logger.debug("Shutting down")


if __name__ == "__main__":
    trio.run(main)
