# holloway

Exact CSG for brutalist interiors, with a live fly-through viewer.

```sh
uv run holloway serve scenes/gallery.py     # opens http://127.0.0.1:8000, rebuilds on save
uv run holloway build scenes/warren.py      # headless: build once, print stats
uv run pytest
```

The scene library is pure Python with only the standard library: no numpy and no
mesh library. The viewer uses three.js, vendored in `holloway/static/vendor/`.

## Writing a scene

A scene is a Python file that defines a module-level `scene`, which can be a
`Scene`, a `Volume`, or a list of volumes.

```python
from fractions import Fraction as F
from holloway import UNIVERSE, Scene, box, halfspace, prism

hall = box((0, 24), (0, 9), (0, 6))                 # intervals...
cell = box(4, 4, 3).translate(x=30)                 # ...or sizes from the origin
door = box((24, F("24.5")), (3, F("4.2")), (0, "2.2"))

world = UNIVERSE - [hall, cell, door]               # carve voids out of infinite concrete
world |= box((10, 18), (0, 2), (0, 3)) & halfspace((-3, 0, 8), through=(10, 0, 0))  # a ramp

scene = Scene().add(world).spawn(at=(1, 2, 1.7), look=(12, 6, 2))
```

- **Exact numbers.** Use ints, `Fraction`s or strings like `"2.2"` and `"1/3"`. Floats
  are refused, so anything you intended to be coplanar *is* coplanar.
- **Set algebra.** `|` is union, `&` intersection, `-` difference and `~` complement.
  `UNIVERSE` and `EMPTY` exist, and finiteness is tracked exactly (`is_finite()`,
  `is_empty()`, `is_universe()`). A list on the right of an operator means the union
  of its items.
- **Primitives:**
  - `box(x, y, z)`
  - `prism(profile, axis, span)`: any simple 2D polygon, extruded.
  - `polytope(*halfspaces)`: any bounded convex shape.
  - `vol & halfspace(...)`: cut a finite volume by a plane, for ramps, tapers and chamfers.
- **Transforms** (exact, about the origin): `translate`, `scale`, `mirror(axis)`, and
  `rotate90(axis, turns)`. There are deliberately no arbitrary rotations.
- **Queries:**
  - `volume()` is an exact `Fraction`.
  - `bounds()` and `contains(p)`.
  - `faces()` returns a `Face` per oriented plane, with `.plane`, `.normal`,
    `.facing(UP)`, `.is_coplanar(plane)` and `.outline()`.
  - `Plane` supports `is_parallel`, `is_coplanar`, `is_orthogonal` and `side(p)`.
- z is up.

Volumes are lazy expressions. Evaluation flattens chains of unions and differences
and merges them in a balanced, spatially sorted order. That means building a scene
in a loop (`w = w - room`) stays fast.

## Viewer

- Click to capture the mouse. **WASD** moves, **Space/E** goes up and **C/Q** down.
  **Shift** is fast, the **mouse wheel** sets speed, **R** respawns and **Esc**
  releases the mouse.
- Lighting modes are ambient (hemisphere plus a soft headlight), sun (a shadowed
  directional light), or both. Each has intensity sliders, and the sun also has
  azimuth and elevation sliders. Slider settings stick per browser; the scene file
  provides the defaults.
- Faces seen from behind are painted plum. If you see plum, you're inside solid.
- On a failed build the last good mesh stays up and the traceback appears on the page.
  The scene script's `print()` output goes to the server's terminal.
- The server watches every `.py` file next to the scene, as well as the holloway
  package itself.

## How it works

- `holloway/geometry.py` is the kernel. Planes are primitive integer tuples
  `(a, b, c, d)`, so equal planes are equal tuples. Vertices are homogeneous integers
  `(X, Y, Z, W)`, so clipping uses only integer arithmetic. Booleans use the csg.js BSP
  algorithm with no epsilons anywhere.
- An infinite set is stored as the flipped boundary of its finite complement, together
  with a `finite` flag.
