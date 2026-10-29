"""Procedural: a grid of cells of random height carved out of infinite concrete,
joined by doorways, with the odd cell sunk a step lower.

    uv run holloway serve scenes/warren.py

Change SEED (or anything else) and save — the browser updates.

The approach is "dig into infinite rock": start from UNIVERSE (solid everywhere) and
subtract every room and doorway. The result is infinite, and its only surfaces are the
inside walls of the voids, which is exactly what you see when walking around inside.
"""

import random
from fractions import Fraction as F

from holloway import UNIVERSE, UP, Scene, box

SEED = 8
N = 6  # cells per side, so 6 x 6 = 36 rooms
CELL = 5  # grid pitch: a room's width plus one wall
WALL = F("0.4")  # wall thickness: exact 2/5, not the float 0.4

# A dedicated, seeded generator, so the same SEED always gives the same layout.
rng = random.Random(SEED)
# Everything to dig out goes in one flat list of boxes.
voids = []
for i in range(N):
    for j in range(N):
        # The cell's south-west corner on the grid.
        x0, y0 = i * CELL, j * CELL
        # 1 in 5 cells has its floor sunk to z = -1, which makes a step at its doorways.
        floor = -1 if rng.random() < 0.2 else 0
        # Ceiling height, weighted toward 3 m, with the occasional 4 m or 6 m tall room.
        height = rng.choice([3, 3, 4, 6])
        # The room: 4.6 x 4.6 m. It stops WALL short of the next grid line, and that
        # strip of undug rock is the wall shared with the neighbour to the east or north.
        voids.append(
            box((x0, x0 + CELL - WALL), (y0, y0 + CELL - WALL), (floor, height))
        )
        # Doorways east and north, at a random offset along the wall.
        # East door: spans exactly the wall's thickness in x (from x0 + 4.6 to x0 + 5),
        # 1.2 m wide in y and 2.4 m tall. Skipped on the last column, which has no
        # neighbour to the east, and randomly skipped 20% of the time.
        if i < N - 1 and rng.random() < 0.8:
            d = rng.randint(1, CELL - 3)  # how far along the wall the door starts
            voids.append(
                box(
                    (x0 + CELL - WALL, x0 + CELL),
                    (y0 + d, y0 + d + F("1.2")),
                    (0, F("2.4")),
                )
            )
        # North door: the same idea with x and y swapped.
        if j < N - 1 and rng.random() < 0.8:
            d = rng.randint(1, CELL - 3)
            voids.append(
                box(
                    (x0 + d, x0 + d + F("1.2")),
                    (y0 + CELL - WALL, y0 + CELL),
                    (0, F("2.4")),
                )
            )

# Dig everything out of infinite solid in one go (the list means "the union of these").
# Overlaps don't matter: a door box overlaps two rooms, and the union simply merges them.
world = UNIVERSE - voids

# Queries are exact: e.g. every upward-facing face is a floor or a step tread.
# faces() groups the boundary by plane, so all the z = 0 floors count as one face and
# all the sunk z = -1 floors as another: "2 distinct floor planes". A procedural
# generator could use queries like this to, say, place lights on every floor.
floors = [f for f in world.faces() if f.facing(UP)]
print(
    f"{len(voids)} voids, {len(floors)} distinct floor planes, infinite={world.is_infinite()}"
)

# Infinite volumes mesh fine: only their (finite) inner surfaces are drawn. Start at
# eye height (1.7 m) in the first room, looking east along the row.
# Note: the rooms are sealed in rock, so sunlight can't reach them. Use the viewer's
# Ambient mode here.
scene = Scene().add(world).spawn(at=(1, 2, F("1.7")), look=(20, 3, F("1.5")))
