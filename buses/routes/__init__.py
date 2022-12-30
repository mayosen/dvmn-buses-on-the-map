import json
from itertools import islice
from pathlib import Path
from typing import Iterable, Any


def _load_paths() -> dict[str, Path]:
    folder = Path(__file__).parent
    files = folder.glob("**/*.json")
    paths = {}
    for file in files:
        paths[file.name.removesuffix(".json")] = file
    return paths


_paths = _load_paths()
_cache = {}


def get_route_names(limit: int) -> Iterable[str]:
    if limit == 0:
        limit = None
    return islice(_paths.keys(), limit)


def _read_route(name: str) -> dict[str, Any]:
    path = _paths[name]
    with open(path, "r", encoding="utf8") as file:
        route = json.load(file)
        _cache[name] = route
        return route


def get_route(name: str) -> dict[str, Any]:
    return _cache.get(name, None) or _read_route(name)
