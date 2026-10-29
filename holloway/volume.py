"""Public construction API: lazy CSG expressions over exact solids.

    room = box((0, 6), (0, 4), (0, 3))
    world = UNIVERSE - room              # carve a void out of infinite concrete
    world -= box((6, 7), (1, 3), (0, "2.2"))   # a doorway

Operators: `a | b` union, `a & b` intersection, `a - b` difference, `~a` complement.
A list of volumes on the right of an operator means their union: `UNIVERSE - rooms`.
Coordinates are exact: ints, Fractions, or strings like "2.2" / "1/3" (floats are refused).
The z axis points up.
"""

from collections.abc import Iterable
from fractions import Fraction
from functools import cached_property

from .geometry import (
    EMPTY_SOLID,
    UNIVERSE_SOLID,
    Affine,
    Point,
    Polygon,
    Solid,
    box_solid,
    make_plane,
    point,
    polytope_solid,
    prism_solid,
    q,
)

AXES = {"x": 0, "y": 1, "z": 2}

UP = (0, 0, 1)
DOWN = (0, 0, -1)
EAST = (1, 0, 0)
WEST = (-1, 0, 0)
NORTH = (0, 1, 0)
SOUTH = (0, -1, 0)


class Plane:
    """An oriented plane n·x = d, normalized so equal planes compare equal."""

    __slots__ = ("key",)

    def __init__(self, normal, offset=0) -> None:
        self.key = make_plane(point(normal), q(offset))

    @classmethod
    def _from_key(cls, key) -> Plane:
        p = cls.__new__(cls)
        p.key = key
        return p

    @classmethod
    def through(cls, p0, p1, p2) -> Plane:
        """Plane through three points; normal by the right-hand rule p0->p1->p2."""
        from .geometry import cross, dot, sub

        a, b, c = point(p0), point(p1), point(p2)
        n = cross(sub(b, a), sub(c, a))
        return cls(n, dot(n, a))

    @classmethod
    def xy(cls, z=0) -> Plane:
        return cls(UP, z)

    @classmethod
    def yz(cls, x=0) -> Plane:
        return cls(EAST, x)

    @classmethod
    def xz(cls, y=0) -> Plane:
        return cls(NORTH, y)

    @property
    def normal(self) -> tuple[int, int, int]:
        return self.key[:3]

    @property
    def offset(self) -> int:
        return self.key[3]

    def flipped(self) -> Plane:
        return Plane._from_key(tuple(-v for v in self.key))

    def _unoriented(self):
        k = self.key
        lead = next(v for v in k if v != 0)
        return k if lead > 0 else tuple(-v for v in k)

    def is_parallel(self, other: Plane) -> bool:
        from .geometry import cross

        return not any(cross(self.normal, other.normal))

    def is_coplanar(self, other: Plane) -> bool:
        """Same plane, regardless of orientation."""
        return self._unoriented() == other._unoriented()

    def is_orthogonal(self, other: Plane) -> bool:
        from .geometry import dot

        return dot(self.normal, other.normal) == 0

    def side(self, p) -> int:
        """+1 in front (the side the normal points to), -1 behind, 0 on the plane."""
        from .geometry import dot

        s = dot(self.normal, point(p)) - self.offset
        return (s > 0) - (s < 0)

    def __eq__(self, other) -> bool:
        return isinstance(other, Plane) and self.key == other.key

    def __hash__(self) -> int:
        return hash(self.key)

    def __repr__(self) -> str:
        a, b, c, d = self.key
        return f"Plane({a}x + {b}y + {c}z = {d})"


class Face:
    """All boundary polygons of a volume lying on one oriented plane."""

    def __init__(self, plane: Plane, polygons: list[Polygon]) -> None:
        self.plane = plane
        self.polygons = polygons

    @property
    def normal(self) -> tuple[int, int, int]:
        """Primitive integer outward normal; axis-aligned faces compare equal to UP etc."""
        return self.plane.normal

    def is_coplanar(self, plane: Plane) -> bool:
        return self.plane.is_coplanar(plane)

    def facing(self, direction) -> bool:
        return self.plane.normal == make_plane(point(direction), 0)[:3]

    def bounds(self) -> tuple[Point, Point]:
        from .geometry import bbox_of

        return bbox_of(self.polygons)

    def outline(self) -> list[tuple[Point, Point]]:
        """Exact boundary segments of this face (internal fragment seams removed)."""
        from .geometry import face_outline

        return face_outline(self.polygons)

    def __repr__(self) -> str:
        return f"Face({self.plane!r}, {len(self.polygons)} polygons)"


class Volume:
    """A lazily evaluated point set. Immutable; operators build new expressions."""

    # --- set algebra ---

    def __or__(self, other) -> Volume:
        return Union((self, _volume(other)))

    def __and__(self, other) -> Volume:
        if isinstance(other, HalfSpace):
            return other & self
        return Intersection((self, _volume(other)))

    def __sub__(self, other) -> Volume:
        if isinstance(other, HalfSpace):
            return (~other) & self
        return Intersection((self, Complement(_volume(other))))

    def __invert__(self) -> Volume:
        return Complement(self)

    union = __or__
    intersect = __and__
    difference = __sub__
    complement = __invert__

    # --- transforms (all exact, about the origin) ---

    def transform(self, m, t=(0, 0, 0)) -> Volume:
        return Transformed(self, Affine(m, t))

    def translate(self, x=0, y=0, z=0) -> Volume:
        return self.transform(((1, 0, 0), (0, 1, 0), (0, 0, 1)), (x, y, z))

    def scale(self, x=1, y=None, z=None) -> Volume:
        y = x if y is None else y
        z = x if z is None else z
        return self.transform(((x, 0, 0), (0, y, 0), (0, 0, z)))

    def mirror(self, axis: str) -> Volume:
        s = [1, 1, 1]
        s[AXES[axis]] = -1
        return self.scale(*s)

    def rotate90(self, axis: str = "z", turns: int = 1) -> Volume:
        """Rotate counter-clockwise (right-hand rule) by `turns` quarter turns."""
        k = AXES[axis]
        i, j = [(1, 2), (2, 0), (0, 1)][k]
        v: Volume = self
        for _ in range(turns % 4):
            m = [[0] * 3 for _ in range(3)]
            m[k][k] = 1
            m[i][j] = -1
            m[j][i] = 1
            v = v.transform(m)
        return v

    # --- evaluation & queries ---

    @cached_property
    def solid(self) -> Solid:
        return self._evaluate()

    def _evaluate(self) -> Solid:
        raise NotImplementedError

    def is_finite(self) -> bool:
        return self.solid.finite

    def is_infinite(self) -> bool:
        return not self.solid.finite

    def is_empty(self) -> bool:
        return self.solid.finite and not self.solid.polys

    def is_universe(self) -> bool:
        return not self.solid.finite and not self.solid.polys

    def volume(self) -> Fraction | float:
        """Exact volume; float('inf') for infinite sets."""
        return self.solid.volume() if self.solid.finite else float("inf")

    def bounds(self) -> tuple[Point, Point] | None:
        """Bounding box of the boundary (for an infinite set: of the holes in it)."""
        return self.solid.bbox

    def faces(self) -> list[Face]:
        groups: dict = {}
        for p in self.solid.polys:
            groups.setdefault(p.plane, []).append(p)
        return [Face(Plane._from_key(k), ps) for k, ps in groups.items()]

    patches = faces

    def contains(self, p) -> bool:
        """Is point p inside (or on the boundary of) the volume?"""
        p = point(p)
        node = self.solid.tree
        if node is None:
            return not self.solid.finite
        while True:
            a, b, c, d = node.plane
            s = a * p[0] + b * p[1] + c * p[2] - d
            nxt = node.back if s <= 0 else node.front
            if nxt is None:
                return s <= 0
            node = nxt

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"


def _volume(v) -> Volume:
    """Volumes pass through; a list/tuple of volumes means their union."""
    if isinstance(v, Volume):
        return v
    if isinstance(v, list | tuple):
        return Union(tuple(_volume(x) for x in v)) if v else EMPTY
    raise TypeError(f"expected a Volume (or a list of them), got {type(v).__name__}")


class Leaf(Volume):
    def __init__(self, solid: Solid, label: str = "solid") -> None:
        self.__dict__["solid"] = solid
        self.label = label

    def _evaluate(self) -> Solid:
        return self.solid

    def __repr__(self) -> str:
        return f"<{self.label}>"


class Complement(Volume):
    def __init__(self, inner: Volume) -> None:
        self.inner = inner

    def _evaluate(self) -> Solid:
        return self.inner.solid.complement()


class Transformed(Volume):
    def __init__(self, inner: Volume, affine: Affine) -> None:
        self.inner = inner
        self.affine = affine

    def _evaluate(self) -> Solid:
        return self.affine.apply_solid(self.inner.solid)


class Union(Volume):
    def __init__(self, children: tuple[Volume, ...]) -> None:
        self.children = children

    def _evaluate(self) -> Solid:
        return union_all([c.solid for c in _flatten(self, Union)])


class Intersection(Volume):
    def __init__(self, children: tuple[Volume, ...]) -> None:
        self.children = children

    def _evaluate(self) -> Solid:
        # a & ~b & ~c & d  ==  (a & d) - (b | c): one big union, one difference.
        pos, neg = [], []
        for c in _flatten(self, Intersection):
            if isinstance(c, Complement) and "solid" not in c.__dict__:
                neg.append(c.inner)
            else:
                pos.append(c)
        if pos:
            base = union_all([p.solid.complement() for p in pos]).complement()
        else:
            base = UNIVERSE_SOLID
        if not neg:
            return base
        holes = union_all([n.solid for n in _flatten_many(neg, Union)])
        return base.difference(holes)


def _flatten(v: Volume, kind: type) -> list[Volume]:
    return _flatten_many([v], kind)


def _flatten_many(vs: list[Volume], kind: type) -> list[Volume]:
    """Expand nested nodes of `kind` (iteratively; loops can build deep chains)."""
    out, stack = [], list(reversed(vs))
    while stack:
        v = stack.pop()
        if type(v) is kind and "solid" not in v.__dict__:
            stack.extend(reversed(v.children))  # type: ignore[attr-defined]
        else:
            out.append(v)
    return out


def union_all(solids: list[Solid]) -> Solid:
    """Balanced, spatially sorted pairwise union (keeps bbox culling effective)."""
    solids = [s for s in solids if s.polys or not s.finite]
    if any(not s.finite and not s.polys for s in solids):
        return UNIVERSE_SOLID
    if not solids:
        return EMPTY_SOLID

    def key(s: Solid):
        lo, hi = s.bbox
        return (lo[0] + hi[0], lo[1] + hi[1], lo[2] + hi[2])

    solids.sort(key=key)
    while len(solids) > 1:
        nxt = [solids[i].union(solids[i + 1]) for i in range(0, len(solids) - 1, 2)]
        if len(solids) % 2:
            nxt.append(solids[-1])
        solids = nxt
    return solids[0]


class HalfSpace:
    """{x : n·x <= d} — the solid lies *behind* the normal.

    Infinite and not a Volume; use it to cut finite volumes:
        ramp = box((0, 6), (0, 2), (0, 3)) & halfspace((-1, 0, 2), through=(0, 0, 0))
    """

    def __init__(self, plane: Plane) -> None:
        self.plane = plane

    def __invert__(self) -> HalfSpace:
        return HalfSpace(self.plane.flipped())

    def __and__(self, other) -> Volume:
        if isinstance(other, HalfSpace):
            raise TypeError("intersect half-spaces via polytope(...)")
        v = _volume(other)
        if v.is_empty():
            return v
        if v.is_infinite():
            raise ValueError("can only cut finite volumes with a half-space")
        lo, hi = v.bounds()
        planes = [make_plane((-1, 0, 0), -(lo[0] - 1)), make_plane((1, 0, 0), hi[0] + 1),
                  make_plane((0, -1, 0), -(lo[1] - 1)), make_plane((0, 1, 0), hi[1] + 1),
                  make_plane((0, 0, -1), -(lo[2] - 1)), make_plane((0, 0, 1), hi[2] + 1),
                  self.plane.key]  # fmt: skip
        return Intersection((v, Leaf(polytope_solid(planes), "halfspace")))

    __rand__ = __and__

    def __rsub__(self, other) -> Volume:
        return (~self) & other


# --- primitives -----------------------------------------------------------------


def _interval(v) -> tuple[Fraction, Fraction]:
    if isinstance(v, tuple | list):
        a, b = q(v[0]), q(v[1])
        return (min(a, b), max(a, b))
    return (Fraction(0), q(v))


def box(x, y, z) -> Volume:
    """Axis-aligned box. Each argument is an interval (lo, hi) or a size (from 0)."""
    (x0, x1), (y0, y1), (z0, z1) = _interval(x), _interval(y), _interval(z)
    return Leaf(box_solid((x0, y0, z0), (x1, y1, z1)), "box")


def prism(profile: Iterable, axis: str = "z", span=(0, 1)) -> Volume:
    """Extrude a simple polygon along an axis.

    `profile` uses the other two axes in natural order: axis z -> (x, y),
    axis y -> (x, z), axis x -> (y, z). `span` is an interval or a length.
    """
    pts = [(q(a), q(b)) for a, b in profile]
    w0, w1 = _interval(span)
    return Leaf(prism_solid(pts, AXES[axis], w0, w1), "prism")


def halfspace(normal, offset=None, *, through=None) -> HalfSpace:
    """{x : normal·x <= offset}; or give a point the boundary passes `through`."""
    if (offset is None) == (through is None):
        raise TypeError("give exactly one of offset or through=")
    if through is not None:
        from .geometry import dot

        offset = dot(point(normal), point(through))
    return HalfSpace(Plane(normal, offset))


def polytope(*halfspaces: HalfSpace) -> Volume:
    """Bounded convex polyhedron: the intersection of the given half-spaces."""
    return Leaf(polytope_solid([h.plane.key for h in halfspaces]), "polytope")


UNIVERSE: Volume = Leaf(UNIVERSE_SOLID, "universe")
EMPTY: Volume = Leaf(EMPTY_SOLID, "empty")
