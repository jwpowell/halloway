"""Exact rational geometry kernel: planes, convex polygons, BSP clipping.

Everything here is exact. Planes are stored as primitive integer tuples
(a, b, c, d) meaning a*x + b*y + c*z = d, with the normal (a, b, c) pointing
*out* of the solid. Two planes are the same plane iff their tuples are equal.

A Solid is a closed, consistently oriented set of convex polygons plus a
`finite` flag. The flag disambiguates the polygon-less cases (empty vs
universe) and tells us what lies "at infinity". Booleans follow the csg.js
algorithm (Evan Wallace), which is robust once arithmetic is exact.
"""

import numbers
from fractions import Fraction
from math import gcd, lcm

type Point = tuple[Fraction, Fraction, Fraction]
type HPoint = tuple[int, int, int, int]  # homogeneous (X, Y, Z, W), W > 0, gcd 1
type PlaneKey = tuple[int, int, int, int]
type BBox = tuple[Point, Point]


def q(value) -> Fraction:
    """Coerce a user-supplied number to an exact Fraction."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        raise TypeError("bool is not a coordinate")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str):
        return Fraction(value)
    if isinstance(value, float):
        raise TypeError(
            f"float {value!r} is not exact; use an int, Fraction, or a string like '0.1' or '1/3'"
        )
    if isinstance(value, numbers.Rational):
        return Fraction(value)
    raise TypeError(f"cannot use {value!r} as an exact coordinate")


def point(p) -> Point:
    x, y, z = p
    return (q(x), q(y), q(z))


def hom(p: Point) -> HPoint:
    """Canonical homogeneous integer form of an exact point."""
    w = lcm(p[0].denominator, p[1].denominator, p[2].denominator)
    return (int(p[0] * w), int(p[1] * w), int(p[2] * w), w)


def cart(h: HPoint) -> Point:
    w = h[3]
    return (Fraction(h[0], w), Fraction(h[1], w), Fraction(h[2], w))


def sub(u: Point, v: Point) -> Point:
    return (u[0] - v[0], u[1] - v[1], u[2] - v[2])


def cross(u, v):
    return (
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    )


def dot(u, v):
    return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]


def primitive(*values) -> tuple[int, ...]:
    """Scale rationals to the unique coprime integer tuple with the same signs."""
    fracs = [Fraction(v) for v in values]
    den = lcm(*(f.denominator for f in fracs))
    ints = [int(f * den) for f in fracs]
    g = gcd(*ints)
    if g == 0:
        raise ValueError("zero vector")
    return tuple(i // g for i in ints)


def make_plane(normal, d) -> PlaneKey:
    a, b, c = normal
    if a == 0 and b == 0 and c == 0:
        raise ValueError("degenerate plane: zero normal")
    return primitive(a, b, c, d)  # type: ignore[return-value]


def newell_plane(verts: tuple[Point, ...]) -> PlaneKey:
    """Plane of a planar polygon, oriented by its (counter-clockwise) winding."""
    nx = ny = nz = Fraction(0)
    n = len(verts)
    for i in range(n):
        x0, y0, z0 = verts[i]
        x1, y1, z1 = verts[(i + 1) % n]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return make_plane((nx, ny, nz), dot((nx, ny, nz), verts[0]))


class Polygon:
    """A convex planar polygon, wound counter-clockwise around its outward normal.

    Vertices are homogeneous integer points so the clipping hot path is integer-only.
    """

    __slots__ = ("verts", "plane", "_bbox")

    def __init__(self, verts: tuple[HPoint, ...], plane: PlaneKey) -> None:
        self.verts = verts
        self.plane = plane
        self._bbox: BBox | None = None

    @classmethod
    def of(cls, points, plane: PlaneKey) -> Polygon:
        return cls(tuple(hom(p) for p in points), plane)

    @property
    def points(self) -> list[Point]:
        return [cart(h) for h in self.verts]

    def flipped(self) -> Polygon:
        a, b, c, d = self.plane
        return Polygon(self.verts[::-1], (-a, -b, -c, -d))

    @property
    def bbox(self) -> BBox:
        if self._bbox is None:
            xs, ys, zs = zip(*self.points)
            self._bbox = ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))
        return self._bbox


def split(poly: Polygon, plane: PlaneKey, cofront: list, coback: list, front: list, back: list) -> None:
    """Classify `poly` against `plane`, splitting it if it straddles."""
    a, b, c, d = plane
    verts = poly.verts
    sides = [a * x + b * y + c * z - d * w for x, y, z, w in verts]
    has_front = any(s > 0 for s in sides)
    has_back = any(s < 0 for s in sides)
    if not has_front and not has_back:
        pa, pb, pc, _ = poly.plane
        (cofront if pa * a + pb * b + pc * c > 0 else coback).append(poly)
    elif not has_back:
        front.append(poly)
    elif not has_front:
        back.append(poly)
    else:
        f: list[HPoint] = []
        bk: list[HPoint] = []
        n = len(verts)
        for i in range(n):
            vi, si = verts[i], sides[i]
            vj, sj = verts[(i + 1) % n], sides[(i + 1) % n]
            if si >= 0:
                f.append(vi)
            if si <= 0:
                bk.append(vi)
            if (si > 0 and sj < 0) or (si < 0 and sj > 0):
                # sides are scaled by W, so this is the exact homogeneous crossing point.
                h = [si * vj[k] - sj * vi[k] for k in range(4)]
                g = gcd(*h)
                if h[3] < 0:
                    g = -g
                v = (h[0] // g, h[1] // g, h[2] // g, h[3] // g)
                f.append(v)
                bk.append(v)
        front.append(Polygon(tuple(f), poly.plane))
        back.append(Polygon(tuple(bk), poly.plane))


class Node:
    """BSP node. A missing front child is empty space; a missing back child is solid."""

    __slots__ = ("plane", "front", "back")

    def __init__(self, plane: PlaneKey) -> None:
        self.plane = plane
        self.front: Node | None = None
        self.back: Node | None = None


def build_tree(polys: list[Polygon]) -> Node | None:
    if not polys:
        return None
    root = Node(polys[len(polys) // 2].plane)
    stack = [(root, polys)]
    while stack:
        node, ps = stack.pop()
        front: list[Polygon] = []
        back: list[Polygon] = []
        coplanar: list[Polygon] = []
        for p in ps:
            split(p, node.plane, coplanar, coplanar, front, back)
        if front:
            node.front = Node(front[len(front) // 2].plane)
            stack.append((node.front, front))
        if back:
            node.back = Node(back[len(back) // 2].plane)
            stack.append((node.back, back))
    return root


def clip_tree(polys: list[Polygon], root: Node) -> list[Polygon]:
    """Keep the parts of `polys` outside the solid described by `root`.

    Coplanar polygons facing the same way as a boundary are kept; facing the
    opposite way they are discarded.
    """
    out: list[Polygon] = []
    stack = [(root, polys)]
    while stack:
        node, ps = stack.pop()
        front: list[Polygon] = []
        back: list[Polygon] = []
        for p in ps:
            split(p, node.plane, front, back, front, back)
        if node.front is not None:
            if front:
                stack.append((node.front, front))
        else:
            out.extend(front)
        if node.back is not None and back:
            stack.append((node.back, back))
    return out


def bbox_of(polys: list[Polygon]) -> BBox:
    los, his = zip(*(p.bbox for p in polys))
    xs0, ys0, zs0 = zip(*los)
    xs1, ys1, zs1 = zip(*his)
    return ((min(xs0), min(ys0), min(zs0)), (max(xs1), max(ys1), max(zs1)))


def disjoint(a: BBox, b: BBox) -> bool:
    """True if the closed boxes do not touch at all."""
    (alo, ahi), (blo, bhi) = a, b
    return any(ahi[i] < blo[i] or bhi[i] < alo[i] for i in range(3))


class Solid:
    """An evaluated, immutable volume: oriented boundary polygons + finiteness."""

    __slots__ = ("polys", "finite", "_tree", "_bbox")

    def __init__(self, polys: list[Polygon], finite: bool) -> None:
        self.polys = polys
        self.finite = finite
        self._tree: Node | None = None
        self._bbox: BBox | None = None

    @property
    def bbox(self) -> BBox | None:
        if self._bbox is None and self.polys:
            self._bbox = bbox_of(self.polys)
        return self._bbox

    @property
    def tree(self) -> Node | None:
        if self._tree is None:
            self._tree = build_tree(self.polys)
        return self._tree

    def complement(self) -> Solid:
        s = Solid([p.flipped() for p in self.polys], not self.finite)
        s._bbox = self._bbox
        return s

    def clip(self, polys: list[Polygon]) -> list[Polygon]:
        """Keep the parts of `polys` lying outside this solid."""
        if not self.polys:
            return list(polys) if self.finite else []
        box = self.bbox
        out: list[Polygon] = []
        todo: list[Polygon] = []
        for p in polys:
            if disjoint(p.bbox, box):
                # Far from our boundary: outside if we're finite, inside if not.
                if self.finite:
                    out.append(p)
            else:
                todo.append(p)
        if todo:
            out.extend(clip_tree(todo, self.tree))
        return out

    def union(self, other: Solid) -> Solid:
        a = other.clip(self.polys)
        b = self.clip(other.polys)
        # Drop b's faces that duplicate a's coplanar same-facing faces.
        b = [p.flipped() for p in self.clip([p.flipped() for p in b])]
        return Solid(a + b, self.finite and other.finite)

    def intersection(self, other: Solid) -> Solid:
        return self.complement().union(other.complement()).complement()

    def difference(self, other: Solid) -> Solid:
        return self.complement().union(other).complement()

    def volume(self) -> Fraction:
        """Exact enclosed volume (divergence theorem). Requires finite."""
        total = Fraction(0)
        for p in self.polys:
            pts = p.points
            for i in range(1, len(pts) - 1):
                total += dot(pts[0], cross(pts[i], pts[i + 1]))
        return total / 6


EMPTY_SOLID = Solid([], True)
UNIVERSE_SOLID = Solid([], False)


# --- Primitive construction -------------------------------------------------


def box_solid(lo: Point, hi: Point) -> Solid:
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    if not (x0 < x1 and y0 < y1 and z0 < z1):
        return EMPTY_SOLID
    quads = [
        ([(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)], (-1, 0, 0, -x0)),
        ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (1, 0, 0, x1)),
        ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (0, -1, 0, -y0)),
        ([(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)], (0, 1, 0, y1)),
        ([(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)], (0, 0, -1, -z0)),
        ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1, z1)),
    ]
    return Solid([Polygon.of(v, make_plane(pl[:3], pl[3])) for v, pl in quads], True)


def _hull_2d(pts: list[tuple[Fraction, Fraction]]) -> list[tuple[Fraction, Fraction]]:
    """Andrew's monotone chain; counter-clockwise, collinear points removed."""
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list = []
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


# For a dropped axis k, the remaining axes in cyclic order (so 2D CCW == +k normal).
_CYCLIC = {0: (1, 2), 1: (2, 0), 2: (0, 1)}


def convex_face(points: list[Point], plane: PlaneKey) -> Polygon | None:
    """Order coplanar points into a convex polygon wound around `plane`'s normal."""
    k = max(range(3), key=lambda i: abs(plane[i]))
    u, v = _CYCLIC[k]
    by_2d = {(p[u], p[v]): p for p in points}
    ring = _hull_2d(list(by_2d))
    if len(ring) < 3:
        return None
    verts = [by_2d[uv] for uv in ring]
    if plane[k] < 0:
        verts.reverse()
    return Polygon.of(verts, plane)


def _solve3(p1: PlaneKey, p2: PlaneKey, p3: PlaneKey) -> Point | None:
    n1, n2, n3 = p1[:3], p2[:3], p3[:3]
    det = dot(n1, cross(n2, n3))
    if det == 0:
        return None
    a = cross(n2, n3)
    b = cross(n3, n1)
    c = cross(n1, n2)
    d1, d2, d3 = p1[3], p2[3], p3[3]
    return tuple(Fraction(d1 * a[i] + d2 * b[i] + d3 * c[i], det) for i in range(3))  # type: ignore[return-value]


def polytope_solid(planes: list[PlaneKey]) -> Solid:
    """Bounded intersection of half-spaces {x : a*x+b*y+c*z <= d}."""
    planes = list(dict.fromkeys(planes))
    n = len(planes)
    verts: set[Point] = set()
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                p = _solve3(planes[i], planes[j], planes[k])
                if p is not None and all(dot(pl[:3], p) <= pl[3] for pl in planes):
                    verts.add(p)
    polys = []
    for pl in planes:
        on = [p for p in verts if dot(pl[:3], p) == pl[3]]
        face = convex_face(on, pl)
        if face is not None:
            polys.append(face)
    if not polys:
        return EMPTY_SOLID
    # A closed surface has zero net area vector; anything else is unbounded.
    net = [Fraction(0)] * 3
    for poly in polys:
        pts = poly.points
        for i in range(1, len(pts) - 1):
            c = cross(sub(pts[i], pts[0]), sub(pts[i + 1], pts[0]))
            net = [net[m] + c[m] for m in range(3)]
    if any(net):
        raise ValueError("polytope is unbounded; add more half-spaces (or intersect with a box)")
    return Solid(polys, True)


def _ear_clip(ring: list[tuple[Fraction, Fraction]]) -> list[tuple[int, int, int]]:
    """Triangulate a simple CCW polygon. Returns index triples."""

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    idx = list(range(len(ring)))
    tris = []
    guard = 0
    while len(idx) > 3:
        guard += 1
        if guard > 10 * len(ring) ** 2:
            raise ValueError("prism profile is not a simple polygon")
        for m in range(len(idx)):
            i0, i1, i2 = idx[m - 1], idx[m], idx[(m + 1) % len(idx)]
            a, b, c = ring[i0], ring[i1], ring[i2]
            if turn(a, b, c) <= 0:
                continue
            if any(
                turn(a, b, ring[o]) >= 0 and turn(b, c, ring[o]) >= 0 and turn(c, a, ring[o]) >= 0
                for o in idx
                if o not in (i0, i1, i2)
            ):
                continue
            tris.append((i0, i1, i2))
            idx.pop(m)
            break
    tris.append(tuple(idx))  # type: ignore[arg-type]
    return tris


def prism_solid(profile: list[tuple[Fraction, Fraction]], axis: int, w0: Fraction, w1: Fraction) -> Solid:
    """Extrude a simple 2D polygon along `axis` from w0 to w1.

    Profile coordinates are the two remaining axes in natural order
    (axis z -> (x, y); axis y -> (x, z); axis x -> (y, z)).
    """
    ring = [p for i, p in enumerate(profile) if p != profile[i - 1]]
    if len(ring) < 3 or w0 >= w1:
        return EMPTY_SOLID
    area2 = sum(ring[i - 1][0] * ring[i][1] - ring[i][0] * ring[i - 1][1] for i in range(len(ring)))
    if area2 == 0:
        return EMPTY_SOLID
    if area2 < 0:
        ring.reverse()
    others = [i for i in range(3) if i != axis]

    def embed(uv, w) -> Point:
        out = [Fraction(0)] * 3
        out[others[0]], out[others[1]], out[axis] = uv[0], uv[1], w
        return tuple(out)  # type: ignore[return-value]

    faces: list[tuple[Point, ...]] = []
    for i0, i1, i2 in _ear_clip(ring):
        faces.append((embed(ring[i0], w1), embed(ring[i1], w1), embed(ring[i2], w1)))
        faces.append((embed(ring[i2], w0), embed(ring[i1], w0), embed(ring[i0], w0)))
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        faces.append((embed(a, w0), embed(b, w0), embed(b, w1), embed(a, w1)))
    solid = Solid([Polygon.of(f, newell_plane(f)) for f in faces], True)
    # The embedding may be a reflection (e.g. axis y with (x, z)); fix orientation.
    if solid.volume() < 0:
        solid = Solid([p.flipped() for p in solid.polys], True)
    return solid


# --- Affine maps --------------------------------------------------------------


class Affine:
    """x -> M x + t with exact rational M (invertible)."""

    __slots__ = ("m", "t")

    def __init__(self, m, t) -> None:
        self.m = tuple(tuple(q(v) for v in row) for row in m)
        self.t = point(t)

    def det(self) -> Fraction:
        return dot(self.m[0], cross(self.m[1], self.m[2]))

    def apply(self, p: Point) -> Point:
        m, t = self.m, self.t
        return tuple(dot(m[i], p) + t[i] for i in range(3))  # type: ignore[return-value]

    def apply_plane(self, plane: PlaneKey) -> PlaneKey:
        # n' = M^-T n (any positive multiple will do: use the cofactor matrix * sign(det)).
        m = self.m
        cols = [tuple(m[r][c] for r in range(3)) for c in range(3)]
        cof = [cross(cols[1], cols[2]), cross(cols[2], cols[0]), cross(cols[0], cols[1])]
        n = plane[:3]
        n2 = tuple(sum(cof[r][i] * n[r] for r in range(3)) for i in range(3))
        det = self.det()
        if det < 0:
            n2 = tuple(-v for v in n2)
        # A point on the old plane maps onto the new plane.
        k = max(range(3), key=lambda i: abs(n[i]))
        p0 = [Fraction(0)] * 3
        p0[k] = Fraction(plane[3], n[k])
        return make_plane(n2, dot(n2, self.apply(tuple(p0))))  # type: ignore[arg-type]

    def apply_solid(self, s: Solid) -> Solid:
        if self.det() == 0:
            raise ValueError("transform is singular")
        flip = self.det() < 0
        polys = []
        for p in s.polys:
            verts = [self.apply(v) for v in p.points]
            polys.append(Polygon.of(verts[::-1] if flip else verts, self.apply_plane(p.plane)))
        return Solid(polys, s.finite)


# --- Outlines -------------------------------------------------------------------


def face_outline(polys: list[Polygon]) -> list[tuple[Point, Point]]:
    """Boundary segments of a set of coplanar fragments, with internal seams cancelled.

    Each directed fragment edge is an interval on its supporting line, keyed by
    Plücker coordinates (direction, moment). Seams between neighbouring fragments
    cover the same stretch in both directions and sum to zero, even across
    T-junctions; what remains is the true outline.
    """
    lines: dict = {}
    for poly in polys:
        pts = poly.points
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            d = primitive(*sub(b, a))
            sign = 1
            if next(v for v in d if v != 0) < 0:
                d, sign = tuple(-v for v in d), -1
            key = (d, cross(d, a))
            ta, tb = dot(d, a), dot(d, b)
            ev = lines.setdefault(key, [])
            ev.append((min(ta, tb), sign))
            ev.append((max(ta, tb), -sign))
    segs = []
    for (d, m), events in lines.items():
        net: dict = {}
        for t, delta in events:
            net[t] = net.get(t, 0) + delta
        dd = dot(d, d)
        # Closest point to the origin is (m x d) / |d|^2; the point at parameter t
        # (where t = d·p) is that plus d * t / |d|^2.
        base = cross(m, d)

        def at(t):
            return tuple((base[k] + d[k] * t) / dd for k in range(3))

        count, start = 0, None
        for t, delta in sorted(net.items()):
            before = count
            count += delta
            if before == 0 and count != 0:
                start = t
            elif before != 0 and count == 0 and t != start:
                segs.append((at(start), at(t)))
    return segs
