import json
from pathlib import Path

_folder = Path(__file__).parent


def _read_route(path: Path) -> dict:
    with open(path, "r", encoding="utf8") as file:
        return json.load(file)


def _load_routes():
    # TODO: remove
    folder = Path(__file__).parent
    raw_routes = folder.glob("**/*.json")
    routes = {}

    for raw in raw_routes:
        route = _read_route(raw)
        routes[route["name"]] = route

    return routes


def get_route(name: str):
    return _read_route(_folder / f"{name}.json")
