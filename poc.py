from fractions import Fraction

"""Intention:

This is a scratched together script that is intended to experiment with the user interface surface of a 
3D geometry library for constructing 3D shapes. The particular use case the user has in mind is constructing 
interior architecture, primarily focusing on brutalist elements. the beginning should support axis aligned volumes
since (a simplified) brutalist architecture often relies on rectilinear forms.

Arbitrary polyhedra and more complex shapes will eventually need to be supported since ramps and stairs 
are not orthogonal, tapering of certain structures may be desired, etc.

After the user constructs the volume, they can render it to floating point mesh. 

The use model of this should be:

- A python HTTP server that serves a web app on localhost that renders a mesh that the 
user can usw WASD and mouse to fly through. clipping is fine. lighting should have three 
modes that can be selected in the web app: diffuse lighting for visibility, directional 
lighting to see how real light fixtures or sun casts, both enabled with intensity sliders.

- a python http client that allows the user to send a mesh and lighting information.

- this python framework sketched in this file.

The user opens a browser and views the web app. Then he runs his client app, tweaking the mesh
and lighting, and the the client app sends the mesh to the server which automatically updates in
the browser.

THe overall intent is _eventually_ to create a procedurally generateed interior with these mechanism.

"""


class Volume:
    def intersect(self, other: Volume) -> Volume: ...
    def union(self, other: Volume) -> Volume: ...
    def difference(self, other: Volume) -> Volume: ...
    def complement(self) -> Volume: ...
    def volume(self) -> Fraction: ...

    def is_finite(self) -> bool: ...
    def is_infinite(self) -> bool: ...
    def is_empty(self) -> bool: ...

    @classmethod
    def empty(cls) -> Volume: ...

    @classmethod
    def aab(
        cls,
        x: tuple[Fraction, Fraction],
        y: tuple[Fraction, Fraction],
        z: tuple[Fraction, Fraction],
    ) -> Box:
        """Create an axis-aligned box."""
        return Box(x, y, z)


class Intersection(Volume):
    def __init__(self, a: Volume, b: Volume) -> None:
        ## Probably want this to collapse intersections together since they are associative.
        self.a = a
        self.b = b


class Union(Volume): ...


class Box:
    """An axis-aligned box in three-dimensional space."""

    def __init__(
        self,
        x: tuple[Fraction, Fraction],
        y: tuple[Fraction, Fraction],
        z: tuple[Fraction, Fraction],
    ) -> None:
        self.x = x
        self.y = y
        self.z = z

    def volume(self) -> Fraction:
        dx = self.x[1] - self.x[0]
        dy = self.y[1] - self.y[0]
        dz = self.z[1] - self.z[0]

        return dx * dy * dz

    def intersect(self, other: Volume) -> Volume:
        if not isinstance(other, Box):
            return Intersection(self, other)

        x1 = max(self.x[0], other.x[0])
        y1 = max(self.y[0], other.y[0])
        z1 = max(self.z[0], other.z[0])

        x2 = min(self.x[1], other.x[1])
        y2 = min(self.y[1], other.y[1])
        z2 = min(self.z[1], other.z[1])

        if x1 >= x2 or y1 >= y2 or z1 >= z2:
            return Volume.empty()

        return Box((x1, x2), (y1, y2), (z1, z2))


class Space: ...


def main() -> None:
    s = Space()

    # Garbage parameters just to see what syntax looks like

    b1 = s.aab(x=(0, 1), y=(0, 1), z=(0, Fraction(1)))
    b2 = s.aab(x=(0, Fraction(1)), y=(0, 1), z=(0, Fraction(1)))
    b2 = b2.translate(x=Fraction(1), y=Fraction(0), z=Fraction(0))
    b2 = b2.scale(x=Fraction(2), y=Fraction(1), z=Fraction(1))

    b3 = b1.intersect(b2.complement())

    # also union, difference, and complement operations are available.

    # complement of a finite volume results in an infinite volume. we can test for that.
    # this check should be properly tracked through all set operations.

    # the empty set and the infinite set have no patches.

    # In general space supports arbitrary polyhedra not shown here.

    # Plane parallel to the xy-plane
    p1 = s.xy()

    # Plane parallel to the xy-plane at z=1
    p2 = s.xy(1)

    t1 = p1.is_parallel(p2)
    t2 = p1.is_coplanar(p2)
    t3 = p1.is_orthogonal(p2)

    v1 = p1.normal()
    v2 = p2.normal()
    v3 = v1.cross(v2)

    p3 = s.plane(normal=v3)

    ps1 = b3.patches()

    matched = []
    for patch in ps1:
        if patch.is_coplanar(p3):
            matched.append(patch)


if __name__ == "__main__":
    main()
