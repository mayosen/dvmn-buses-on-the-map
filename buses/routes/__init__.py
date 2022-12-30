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


_route_paths = _load_paths()


def _read_route(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf8") as file:
        return json.load(file)


def get_route(name: str) -> dict[str, Any]:
    return _read_route(_route_paths.get(name))


def get_route_names(limit: int) -> Iterable[str]:
    if limit == 0:
        limit = None
    return islice(_route_paths.keys(), limit)
