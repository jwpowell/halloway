"""Run a scene script and print the resulting scene as JSON.

Run as `python -m holloway.build script.py`. The server uses this in a fresh
subprocess per rebuild, so the script always sees fresh module state.

The script must define a module-level `scene`: a Scene, a Volume, or a list of Volumes.
"""

import json
import runpy
import sys
import time

from .scene import Scene
from .volume import Volume


def load_scene(path: str) -> Scene:
    ns = runpy.run_path(path, run_name="__holloway__")
    if "scene" not in ns:
        raise NameError(f"{path} must define a module-level `scene` (a Scene or Volume)")
    obj = ns["scene"]
    if isinstance(obj, Scene):
        return obj
    if isinstance(obj, Volume):
        return Scene().add(obj)
    if isinstance(obj, list | tuple) and all(isinstance(v, Volume) for v in obj):
        return Scene().add(*obj)
    raise TypeError(f"`scene` must be a Scene or Volume, got {type(obj).__name__}")


def main() -> None:
    t0 = time.perf_counter()
    out, sys.stdout = sys.stdout, sys.stderr  # the script's prints go to the server log
    try:
        scene = load_scene(sys.argv[1])
        data = scene.to_json()
    finally:
        sys.stdout = out
    data["stats"]["build_ms"] = round((time.perf_counter() - t0) * 1000)
    json.dump(data, sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
