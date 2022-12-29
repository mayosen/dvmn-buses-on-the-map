import json
from pathlib import Path
from typing import Iterable

_folder = Path(__file__).parent


def _read_route(path: Path) -> dict:
    with open(path, "r", encoding="utf8") as file:
        return json.load(file)


def _load_routes() -> dict:
    folder = Path(__file__).parent
    files = folder.glob("**/*.json")
    routes = {}

    for file in files:
        route = _read_route(file)
        routes[route["name"]] = route

    return routes


_routes = _load_routes()


def get_route(name: str) -> dict:
    return _routes.get(name, None)


def get_all_route_names() -> list[str]:
    return list(_routes.keys())
