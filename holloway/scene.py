"""Scene: the volumes to show plus default lighting and camera."""

import math
import time

from .geometry import face_outline
from .volume import Volume


class Scene:
    def __init__(self) -> None:
        self.volumes: list[Volume] = []
        self.sun_direction = (-1, -2, -3)  # direction the light travels
        self.sun_intensity = 2.0
        self.ambient_intensity = 1.2
        self.spawn_at = None
        self.spawn_look = None

    def add(self, *volumes: Volume) -> Scene:
        self.volumes.extend(volumes)
        return self

    def sun(self, direction=None, intensity=None) -> Scene:
        if direction is not None:
            self.sun_direction = tuple(float(v) for v in direction)
        if intensity is not None:
            self.sun_intensity = float(intensity)
        return self

    def ambient(self, intensity) -> Scene:
        self.ambient_intensity = float(intensity)
        return self

    def spawn(self, at, look=None) -> Scene:
        """Where the viewer starts (and returns to with R)."""
        self.spawn_at = tuple(float(v) for v in at)
        self.spawn_look = None if look is None else tuple(float(v) for v in look)
        return self

    def to_json(self) -> dict:
        t0 = time.perf_counter()
        meshes = []
        lo = [math.inf] * 3
        hi = [-math.inf] * 3
        polygons = 0
        for v in self.volumes:
            if v.is_universe():
                raise ValueError("cannot mesh the universal set: it has no boundary")
            positions: list[float] = []
            for poly in v.solid.polys:
                vs = [(x / w, y / w, z / w) for x, y, z, w in poly.verts]
                for p in vs:
                    for i in range(3):
                        lo[i] = min(lo[i], p[i])
                        hi[i] = max(hi[i], p[i])
                for i in range(1, len(vs) - 1):
                    positions.extend(vs[0])
                    positions.extend(vs[i])
                    positions.extend(vs[i + 1])
            polygons += len(v.solid.polys)
            # Each crease appears in the outlines of both faces meeting there; draw it once.
            segments = set()
            for face in v.faces():
                for a, b in face_outline(face.polygons):
                    segments.add((a, b) if a <= b else (b, a))
            lines = [float(c) for seg in segments for p in seg for c in p]
            meshes.append({"positions": positions, "lines": lines, "infinite": v.is_infinite()})
        if lo[0] == math.inf:
            lo, hi = [0.0] * 3, [1.0] * 3
        return {
            "meshes": meshes,
            "bounds": [lo, hi],
            "sun": {"direction": self.sun_direction, "intensity": self.sun_intensity},
            "ambient": {"intensity": self.ambient_intensity},
            "spawn": None if self.spawn_at is None else {"at": self.spawn_at, "look": self.spawn_look},
            "stats": {
                "polygons": polygons,
                "triangles": sum(len(m["positions"]) for m in meshes) // 9,
                "mesh_ms": round((time.perf_counter() - t0) * 1000),
            },
        }
