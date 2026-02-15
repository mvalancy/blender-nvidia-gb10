"""
Infinite Mirror Room — reflective walls with floating emissive geometric primitives.
Showcases: Perfect mirror reflections, high bounce counts, emission, color theory.
Inspired by Yayoi Kusama's infinity rooms.
"""
import bpy
import math
import random
import time
import os

OUTPUT = "/tmp/blender_renders/infinite_mirrors.png"
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

random.seed(7)


def clear():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def make_mirror(name, tint=(0.95, 0.95, 0.95)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    glossy = nodes.new('ShaderNodeBsdfGlossy')
    glossy.inputs['Color'].default_value = (*tint, 1)
    glossy.inputs['Roughness'].default_value = 0.0
    links.new(glossy.outputs[0], out.inputs[0])
    return mat


def make_emission(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    emit = nodes.new('ShaderNodeEmission')
    emit.inputs['Color'].default_value = (*color, 1)
    emit.inputs['Strength'].default_value = strength
    links.new(emit.outputs[0], out.inputs[0])
    return mat


print("=" * 60)
print("INFINITE MIRROR ROOM")
print("=" * 60)

clear()
t0 = time.time()

mirror_mat = make_mirror("Mirror", (0.97, 0.97, 0.98))
dark_mirror = make_mirror("DarkMirror", (0.85, 0.85, 0.88))

# Build the room — 6 walls (box)
room_size = 4.0
half = room_size / 2

# Floor
bpy.ops.mesh.primitive_plane_add(size=room_size, location=(0, 0, 0))
bpy.context.active_object.data.materials.append(dark_mirror)

# Ceiling
bpy.ops.mesh.primitive_plane_add(size=room_size, location=(0, 0, room_size))
bpy.context.active_object.data.materials.append(mirror_mat)

# Walls
for rot, loc in [
    ((math.radians(90), 0, 0), (0, half, half)),           # Back
    ((math.radians(90), 0, 0), (0, -half, half)),          # Front
    ((0, math.radians(90), 0), (half, 0, half)),            # Right
    ((0, math.radians(90), 0), (-half, 0, half)),           # Left
]:
    bpy.ops.mesh.primitive_plane_add(size=room_size, location=loc, rotation=rot)
    bpy.context.active_object.data.materials.append(mirror_mat)

# Floating emissive orbs — different colors and sizes
orb_colors = [
    (1.0, 0.2, 0.3),   # Red
    (0.2, 0.5, 1.0),   # Blue
    (1.0, 0.8, 0.1),   # Yellow
    (0.2, 1.0, 0.5),   # Green
    (0.8, 0.2, 1.0),   # Purple
    (1.0, 0.5, 0.1),   # Orange
    (0.1, 0.9, 0.9),   # Cyan
    (1.0, 0.3, 0.7),   # Pink
]

objects = []
for i in range(40):
    x = random.uniform(-1.5, 1.5)
    y = random.uniform(-1.5, 1.5)
    z = random.uniform(0.5, 3.5)
    radius = random.uniform(0.05, 0.15)

    # Mix of shapes
    shape = random.choice(['sphere', 'cube', 'torus'])
    if shape == 'sphere':
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=(x, y, z), segments=16, ring_count=12)
    elif shape == 'cube':
        bpy.ops.mesh.primitive_cube_add(size=radius * 1.6, location=(x, y, z))
        bpy.context.active_object.rotation_euler = (
            random.uniform(0, math.pi),
            random.uniform(0, math.pi),
            random.uniform(0, math.pi),
        )
    else:
        bpy.ops.mesh.primitive_torus_add(
            major_radius=radius, minor_radius=radius * 0.35,
            location=(x, y, z)
        )
        bpy.context.active_object.rotation_euler = (
            random.uniform(0, math.pi),
            random.uniform(0, math.pi),
            random.uniform(0, math.pi),
        )

    obj = bpy.context.active_object
    color = orb_colors[i % len(orb_colors)]
    strength = random.uniform(8, 25)
    obj.data.materials.append(make_emission(f"Emissive_{i}", color, strength))
    bpy.ops.object.shade_smooth()
    objects.append(obj)

print(f"Created mirror room with {len(objects)} emissive objects in {time.time()-t0:.1f}s")

# Camera inside the room
bpy.ops.object.camera_add(location=(0.8, -1.2, 1.8))
cam = bpy.context.active_object
bpy.context.scene.camera = cam
cam.data.lens = 24  # Wide angle to see reflections

bpy.ops.object.empty_add(location=(-0.3, 0.5, 2.0))
target = bpy.context.active_object
target.name = "MirrorTarget"
constraint = cam.constraints.new('TRACK_TO')
constraint.target = target
constraint.track_axis = 'TRACK_NEGATIVE_Z'
constraint.up_axis = 'UP_Y'

cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 2.5
cam.data.dof.aperture_fstop = 5.6

# No world light — all illumination from emissive objects
world = bpy.data.worlds.new("MirrorWorld")
bpy.context.scene.world = world
world.use_nodes = True
nodes = world.node_tree.nodes
links = world.node_tree.links
nodes.clear()
out = nodes.new('ShaderNodeOutputWorld')
bg = nodes.new('ShaderNodeBackground')
bg.inputs['Color'].default_value = (0, 0, 0, 1)
bg.inputs['Strength'].default_value = 0
links.new(bg.outputs[0], out.inputs['Surface'])

# Render settings — need high bounce count for mirror reflections
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = 256
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 32       # High for infinite reflections
scene.cycles.glossy_bounces = 24    # Key for mirror recursion
scene.cycles.diffuse_bounces = 4
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_depth = '16'

prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'CUDA'
prefs.get_devices()
for d in prefs.devices:
    d.use = True

scene.render.filepath = OUTPUT

print(f"Rendering 1280x720 @ 256 samples (32 max bounces)...")
t_render = time.time()
bpy.ops.render.render(write_still=True)
t_render = time.time() - t_render

print(f"Done in {t_render:.1f}s ({os.path.getsize(OUTPUT):,} bytes)")
print(f"Output: {OUTPUT}")
