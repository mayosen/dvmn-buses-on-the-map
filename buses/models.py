from dataclasses import dataclass
from enum import Enum
from typing import Any

import jsons
from jsons import UnfulfilledArgumentError


def register_jsons(cls: Any) -> Any:
    serializer = getattr(cls, "serialize")
    deserializer = getattr(cls, "deserialize")
    jsons.set_serializer(serializer, cls)
    jsons.set_deserializer(deserializer, cls)
    return cls


@register_jsons
class MessageType(Enum):
    BUSES = ("Buses", "buses")
    NEW_BOUNDS = ("NewBounds", "data")
    ERRORS = ("Errors", "errors")

    def __init__(self, type_name: str, payload_name: str):
        self.type_name = type_name
        self.payload_name = payload_name

    @staticmethod
    def serialize(obj: "MessageType", **kwargs) -> str:
        return obj.type_name

    @staticmethod
    def deserialize(obj: str, cls: type, **kwargs) -> "MessageType":
        for msg_type in MessageType:
            if msg_type.type_name == obj:
                return msg_type
        raise UnfulfilledArgumentError(f"Incorrect message type '{obj}'", "type_", obj, cls)


@register_jsons
@dataclass(frozen=True)
class Message:
    msg_type: MessageType
    payload: Any

    @classmethod
    def buses(cls, buses: list["Bus"]) -> "Message":
        return cls(MessageType.BUSES, buses)

    @classmethod
    def errors(cls, errors: Any) -> "Message":
        return cls(MessageType.ERRORS, errors)

    @staticmethod
    def serialize(obj: "Message", **kwargs) -> dict[str, Any]:
        msg_type = obj.msg_type
        return {
            "msgType": jsons.dump(msg_type, strict=True),
            msg_type.payload_name: jsons.dump(obj.payload, strict=True),
        }

    @staticmethod
    def deserialize(obj: dict[str, Any], cls: type, **kwargs) -> "Message":
        try:
            msg_type = jsons.load(obj["msgType"], cls=MessageType, strict=True)
            if msg_type.payload_name not in obj:
                raise UnfulfilledArgumentError(f"Payload '{msg_type.payload_name}' expected", "payload", obj, cls)
            payload = obj[msg_type.payload_name]
            return Message(msg_type, payload)
        except KeyError as e:
            field = e.args[0]
            raise UnfulfilledArgumentError(f"Missed field '{field}'", field, obj, cls)


@register_jsons
@dataclass
class Bus:
    route: str
    bus_id: str
    latitude: float | None = None
    longitude: float | None = None

    @staticmethod
    def serialize(obj: "Bus", **kwargs) -> dict[str, Any]:
        return {
            "route": obj.route,
            "busId": obj.bus_id,
            "lat": obj.latitude,
            "lng": obj.longitude,
        }

    @staticmethod
    def deserialize(obj: dict[str, Any], cls: type, **kwargs) -> "Bus":
        try:
            route = obj["route"]
            bus_id = obj["busId"]
            latitude = obj["lat"]
            longitude = obj["lng"]
            return Bus(route, bus_id, latitude, longitude)
        except KeyError as e:
            field = e.args[0]
            raise UnfulfilledArgumentError(f"Missed field '{field}'", field, obj, cls)


@dataclass
class WindowBounds:
    south_latitude: float | None = None
    north_latitude: float | None = None
    west_longitude: float | None = None
    east_longitude: float | None = None
    exists: bool = False

    def update(self, bounds: dict[str, float]):
        self.south_latitude = bounds["south_lat"]
        self.north_latitude = bounds["north_lat"]
        self.west_longitude = bounds["west_lng"]
        self.east_longitude = bounds["east_lng"]
        self.exists = True

    def is_inside(self, bus: Bus) -> bool:
        return (
            self.south_latitude <= bus.latitude <= self.north_latitude
            and self.west_longitude <= bus.longitude <= self.east_longitude
        )
