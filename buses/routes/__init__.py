import json
from itertools import islice
from pathlib import Path
from typing import Iterable, Any


def _load_paths() -> dict[str, Path]:
    folder = Path(__file__).parent
    routes = folder.glob("**/data/*.json")
    paths = {}
    for route in routes:
        paths[route.name.removesuffix(".json")] = route
    return paths


_paths = _load_paths()


def get_route_names(limit: int | None) -> Iterable[str]:
    return islice(_paths.keys(), limit)


def read_route(name: str) -> dict[str, Any]:
    with open(_paths[name], "r", encoding="utf8") as file:
        route = json.load(file)
        return route
