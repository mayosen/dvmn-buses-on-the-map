import json
from pathlib import Path


def _read_route(path: Path) -> dict:
    with open(path, "r") as file:
        return json.load(file)


def _load_routes():
    folder = Path(__file__).parent
    raw_routes = folder.glob("**/*.json")
    routes = {}

    for raw in raw_routes:
        route = _read_route(raw)
        routes[route["name"]] = route

    return routes


_routes = _load_routes()


def get_route(name: str):
    return _routes.get(name, None)
