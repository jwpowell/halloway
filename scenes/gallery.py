"""A small brutalist gallery: a coffered double-height hall, side rooms, a ramp to a
mezzanine, columns, roof light slots and a ribbon window.

    uv run holloway serve scenes/gallery.py

The approach is "sculpt from a block": start with one finite slab of concrete (`mass`),
subtract all the air (`voids`), then add back solid things that stand inside the air
(columns, ramp, mezzanine). Units are meters and z points up.
"""

from fractions import Fraction as F

from holloway import Scene, box, halfspace

# Everything is exact: use ints, Fractions, or strings like "2.2" — never floats.
# F("2.2") is exactly 11/5, so every door top built from DOOR_H lands on one plane.
DOOR_H = F("2.2")
HALL_H = 6

# box(x, y, z) takes one (lo, hi) interval per axis.
# The block the whole building is carved from: 26 x 14 x 8 m. Its edges sit 1 m
# outside the hall on every side, which leaves 1 m thick outer walls, floor and roof.
mass = box((-1, 25), (-1, 13), (-1, 7))
# A wide, thin slab for the building to sit on, so outdoor sun casts shadows somewhere.
# Its top (z = -1) exactly touches the bottom of `mass`, so when they're unioned the
# touching faces cancel and it becomes one continuous piece of concrete.
ground = box((-30, 55), (-30, 45), (-2, -1))

# The main room: 24 x 9 m floor at z = 0, 6 m tall. The roof slab above it runs z 6..7.
hall = box((0, 24), (0, 9), (0, HALL_H))

# Coffered ceiling: a 3 m grid of 2.4 x 2.4 m recesses, each pushed 0.5 m up into the
# roof slab (z 6..6.5). The 0.3 m margin left on each side of every cell becomes a
# 0.6 m beam between neighbouring coffers. This is a plain Python list of 8 x 3 boxes.
coffers = [
    box((x + F("0.3"), x + F("2.7")), (y + F("0.3"), y + F("2.7")), (HALL_H, F("6.5")))
    for x in range(0, 24, 3)
    for y in range(0, 9, 3)
]

# Side rooms north of the hall. The hall ends at y = 9 and the rooms start at y = 9.5,
# so the 0.5 m of mass left between them becomes the dividing wall.
rooms = []
for i in range(4):
    x0 = i * 6
    # A 5.5 x 2.5 m room, 3 m tall. The 0.5 m gaps between rooms are walls too.
    rooms.append(box((x0, x0 + F("5.5")), (F("9.5"), 12), (0, 3)))
    # A 1.2 m wide doorway that cuts just the 0.5 m dividing wall (y 9..9.5), so the room
    # opens into the hall. It's only a void like any other: carving it out is what makes a door.
    rooms.append(box((x0 + 2, x0 + F("3.2")), (9, F("9.5")), (0, DOOR_H)))

# Roof light slots: 0.6 m wide strips running from z 6 (the hall ceiling) to z 7 (the
# roof top), so they punch all the way through to the sky. That lets the sun in.
slots = [box((x, x + F("0.6")), (1, 8), (HALL_H, 7)) for x in (4, 13, 20)]
# Ribbon window: a 0.4 m tall strip through the whole 1 m south wall (y -1..0).
window = box((2, 22), (-1, 0), (F("1.2"), F("1.6")))

# All the air in one Volume. `+` binds tighter than `|`, so this first concatenates the
# Python lists into one big list, then unions the hall with every box in it.
# (A list on the right of a set operator means "the union of all of these".)
voids = hall | coffers + rooms + slots + [window]

# Solid things standing inside the air.
# A 1 m thick mezzanine slab, its top at z = 3, in the hall's east end.
mezzanine = box((18, 24), (0, 3), (2, 3))
# A ramp: take a 8 x 2 x 3 m box and keep only the part under a sloped plane.
# halfspace(normal, through=point) keeps everything *behind* the normal, i.e. where
# -3x + 8z <= -30, which rearranges to z <= 3/8 * (x - 10). That's a slope rising from
# z = 0 at x = 10 to z = 3 at x = 18, exactly meeting the mezzanine's top.
ramp = box((10, 18), (0, 2), (0, 3)) & halfspace((-3, 0, 8), through=(10, 0, 0))
# A row of 0.6 x 0.6 m columns from the floor to the ceiling, down the hall's middle.
columns = [box((x, x + F("0.6")), (F("4.2"), F("4.8")), (0, HALL_H)) for x in (3, 9, 15, 21)]

# The whole building: carve the air out of the block, then add back the ground and the
# solid fittings. Nothing is computed yet; this only builds an expression that holloway
# evaluates (exactly) when the scene is meshed.
solid = (mass - voids) | ground | mezzanine | ramp | columns

# What the viewer shows. The sun direction is the way the light *travels* (here mostly
# downward). spawn is where the camera starts and what it looks at (R in the viewer
# returns you there). Lighting and camera values are only for display, so floats are fine.
scene = Scene().add(solid).sun(direction=(-1, -0.6, -2), intensity=3).spawn(at=(1, 2, 1.7), look=(12, 6, 2))

# Scripts can query geometry too; prints show up in the server's terminal.
# This is the exact volume of air inside the block, as a Fraction (in cubic meters).
print("enclosed void volume:", (voids & mass).volume())
