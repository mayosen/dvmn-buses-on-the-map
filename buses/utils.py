from typing import Any


def generate_id(obj: Any) -> str:
    return hex(id(obj))[-6:]
