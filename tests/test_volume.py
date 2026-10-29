from fractions import Fraction

import pytest

from holloway import DOWN, EMPTY, UNIVERSE, UP, Plane, box, halfspace, polytope, prism


def closed(v) -> bool:
    """Net area vector of a closed surface is zero; a cheap, exact sanity check."""
    from holloway.geometry import cross, sub

    net = [Fraction(0)] * 3
    for p in v.solid.polys:
        pts = p.points
        for i in range(1, len(pts) - 1):
            c = cross(sub(pts[i], pts[0]), sub(pts[i + 1], pts[0]))
            net = [net[k] + c[k] for k in range(3)]
    return not any(net)


def test_box_volume_and_flags():
    b = box(2, 3, 4)
    assert b.volume() == 24
    assert b.is_finite() and not b.is_empty()
    assert box((0, "1/3"), 1, 1).volume() == Fraction(1, 3)


def test_floats_refused():
    with pytest.raises(TypeError):
        box(1.5, 1, 1)


def test_union_overlapping():
    u = box(2, 2, 2) | box((1, 3), 2, 2)
    assert u.volume() == 12
    assert closed(u)


def test_union_touching_merges_faces():
    u = box(1, 1, 1) | box((1, 2), 1, 1)
    assert u.volume() == 2
    # No internal face survives at x = 1.
    assert not any(f.is_coplanar(Plane.yz(1)) for f in u.faces())


def test_union_coplanar_same_facing():
    u = box(2, 2, 1) | box((1, 3), (1, 3), 1)
    assert u.volume() == 7
    floor = [f for f in u.faces() if f.facing(DOWN)]
    assert len(floor) == 1
    assert closed(u)


def test_intersection_and_difference():
    a, b = box(2, 2, 2), box((1, 3), (1, 3), (1, 3))
    assert (a & b).volume() == 1
    assert (a - b).volume() == 7
    assert (b - a).volume() == 7
    assert closed(a - b)


def test_touching_intersection_is_empty():
    assert (box(1, 1, 1) & box((1, 2), 1, 1)).is_empty()


def test_complement_algebra():
    a = box(1, 1, 1)
    assert (~a).is_infinite()
    assert (~~a).volume() == 1
    assert (UNIVERSE - a).is_infinite()
    assert (UNIVERSE - a).volume() == float("inf")
    assert (a | ~a).is_universe()
    assert (a & ~a).is_empty()
    assert (a - UNIVERSE).is_empty()
    assert (a | EMPTY).volume() == 1
    assert (a & UNIVERSE).volume() == 1


def test_carved_world():
    rooms = box(4, 4, 3) | box((4, 8), (1, 3), (0, 2))
    world = UNIVERSE - rooms
    assert world.is_infinite()
    assert (~world).volume() == 4 * 4 * 3 + 4 * 2 * 2
    # A room's floor is a face of the world pointing up into the void.
    assert any(f.facing(UP) and f.is_coplanar(Plane.xy(0)) for f in world.faces())
    assert world.contains((10, 10, 10))
    assert not world.contains((1, 1, 1))


def test_many_differences_flatten():
    slab = box(20, 20, 4)
    v = slab
    for i in range(10):
        v = v - box((2 * i, 2 * i + 1), (1, 19), (1, 3))
    assert v.volume() == 20 * 20 * 4 - 10 * 18 * 2


def test_transforms():
    b = box((1, 2), (0, 3), (0, 1))
    assert b.translate(x=5).bounds() == ((6, 0, 0), (7, 3, 1))
    assert b.scale(2).volume() == 24
    assert b.mirror("x").bounds() == ((-2, 0, 0), (-1, 3, 1))
    assert b.mirror("x").volume() == 3
    r = b.rotate90("z")
    assert r.bounds() == ((-3, 1, 0), (0, 2, 1))
    assert r.volume() == 3
    assert closed(r)


def test_ramp_by_halfspace():
    # Slope rising 1 in 2 along x: keep everything under z = x/2.
    ramp = box(6, 2, 3) & halfspace((-1, 0, 2), through=(0, 0, 0))
    assert ramp.volume() == Fraction(1, 2) * 6 * 3 * 2
    slopes = [f for f in ramp.faces() if f.normal == (-1, 0, 2)]
    assert len(slopes) == 1


def test_prism_l_shape():
    l = prism([(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3)], axis="z", span=(0, 2))
    assert l.volume() == 5 * 2
    side = prism([(0, 0), (4, 0), (4, 2)], axis="y", span=3)  # wedge, (x, z) profile
    assert side.volume() == 4 * 3
    assert closed(side)


def test_polytope_tapered_column():
    col = polytope(
        halfspace(DOWN, 0), halfspace(UP, 4),
        halfspace((-8, 0, 1), 0), halfspace((8, 0, 1), 16),
        halfspace((0, -8, 1), 0), halfspace((0, 8, 1), 16),
    )  # fmt: skip
    # Frustum: 2x2 base, 1x1 top, height 4.
    assert col.volume() == Fraction(4, 3) * (4 + 1 + 2)


def test_planes():
    assert Plane.xy().is_parallel(Plane.xy(1))
    assert not Plane.xy().is_coplanar(Plane.xy(1))
    assert Plane.xy(2).is_coplanar(Plane((0, 0, -3), -6))
    assert Plane.xy().is_orthogonal(Plane.yz())
    assert Plane((0, 0, 2), 4) == Plane.xy(2)


def test_outline_cancels_seams():
    # Two boxes sharing a floor plane: the merged floor is one L-ish region whose
    # outline has no internal seam, no matter how the kernel fragmented it.
    u = box(2, 2, 1) | box((1, 3), (1, 3), 1)
    (floor,) = [f for f in u.faces() if f.facing(DOWN)]
    segs = floor.outline()
    perimeter = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in segs)
    assert perimeter == 12
    assert len(segs) == 8


def test_list_operand_means_union():
    rooms = [box((2 * i, 2 * i + 1), 1, 1) for i in range(5)]
    assert (box(10, 1, 1) - rooms).volume() == 5
    assert (UNIVERSE - rooms).is_infinite()
    assert (box(1, 1, 1) | []).volume() == 1
