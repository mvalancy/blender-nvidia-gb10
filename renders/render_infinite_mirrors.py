"""
Infinite Mirror Corridor — a mirrored hallway with neon edge lighting.
Showcases: Perfect mirror reflections, high bounce counts, emission, perspective depth.
"""
import bpy
import math
import random
import time
import os

OUTPUT = "/tmp/blender_renders/infinite_mirrors.png"
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

random.seed(42)


def clear():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def make_mirror(name, tint=(0.92, 0.92, 0.94)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (*tint, 1)
    bsdf.inputs['Metallic'].default_value = 1.0
    bsdf.inputs['Roughness'].default_value = 0.0
    bsdf.inputs['Specular IOR Level'].default_value = 1.0
    links.new(bsdf.outputs[0], out.inputs[0])
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
print("INFINITE MIRROR CORRIDOR")
print("=" * 60)

clear()
t0 = time.time()

mirror_mat = make_mirror("Mirror")
dark_mirror = make_mirror("DarkMirror", (0.88, 0.88, 0.9))

# Build a long corridor
L = 14.0   # length
W = 2.8    # width
H = 3.2    # height

# Floor
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, L / 2, 0))
floor = bpy.context.active_object
floor.scale = (W / 2, L / 2, 1)
floor.data.materials.append(dark_mirror)

# Ceiling
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, L / 2, H))
ceiling = bpy.context.active_object
ceiling.scale = (W / 2, L / 2, 1)
ceiling.data.materials.append(mirror_mat)

# Left wall
bpy.ops.mesh.primitive_plane_add(
    size=1, location=(-W / 2, L / 2, H / 2), rotation=(0, math.radians(-90), 0)
)
lwall = bpy.context.active_object
lwall.scale = (H / 2, L / 2, 1)
lwall.data.materials.append(mirror_mat)

# Right wall
bpy.ops.mesh.primitive_plane_add(
    size=1, location=(W / 2, L / 2, H / 2), rotation=(0, math.radians(90), 0)
)
rwall = bpy.context.active_object
rwall.scale = (H / 2, L / 2, 1)
rwall.data.materials.append(mirror_mat)

# Back wall (end of corridor — creates infinite depth)
bpy.ops.mesh.primitive_plane_add(
    size=1, location=(0, L, H / 2), rotation=(math.radians(-90), 0, 0)
)
back = bpy.context.active_object
back.scale = (W / 2, H / 2, 1)
back.data.materials.append(mirror_mat)

# Front wall (behind camera)
bpy.ops.mesh.primitive_plane_add(
    size=1, location=(0, -0.05, H / 2), rotation=(math.radians(90), 0, 0)
)
front = bpy.context.active_object
front.scale = (W / 2, H / 2, 1)
front.data.materials.append(mirror_mat)

# Neon colors — saturated and vivid
neon_colors = [
    (1.0, 0.05, 0.2),   # Hot pink
    (0.05, 0.3, 1.0),   # Electric blue
    (0.0, 1.0, 0.4),    # Neon green
    (1.0, 0.4, 0.0),    # Orange
    (0.5, 0.0, 1.0),    # Purple
]

objects = []

# Continuous LED edge strips running the full length of the corridor
# These create the dramatic vanishing-point lines
edge_positions = [
    # (x, z) positions for the 4 corridor edges
    (-W / 2 + 0.01, 0.01),       # bottom-left
    (W / 2 - 0.01, 0.01),        # bottom-right
    (-W / 2 + 0.01, H - 0.01),   # top-left
    (W / 2 - 0.01, H - 0.01),    # top-right
]
edge_colors = [
    (1.0, 0.05, 0.2),   # pink
    (0.05, 0.3, 1.0),   # blue
    (0.5, 0.0, 1.0),    # purple
    (0.0, 1.0, 0.4),    # green
]

for idx, ((ex, ez), ec) in enumerate(zip(edge_positions, edge_colors)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(ex, L / 2, ez))
    strip = bpy.context.active_object
    strip.scale = (0.015, L / 2, 0.015)
    strip.data.materials.append(make_emission(f"Edge_{idx}", ec, 50))
    objects.append(strip)

# Cross-bars at regular intervals — creates the "frame" effect
for i in range(12):
    y = 0.8 + i * 1.1
    color = neon_colors[i % len(neon_colors)]
    strength = 35

    # Ceiling bar
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, y, H - 0.02))
    bar = bpy.context.active_object
    bar.scale = (W * 0.48, 0.012, 0.012)
    bar.data.materials.append(make_emission(f"Ceil_{i}", color, strength))
    objects.append(bar)

    # Floor bar
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, y, 0.02))
    fbar = bpy.context.active_object
    fbar.scale = (W * 0.45, 0.01, 0.01)
    fbar.data.materials.append(make_emission(f"Floor_{i}", color, strength * 0.6))
    objects.append(fbar)

    # Left wall vertical bar
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=(-W / 2 + 0.02, y, H / 2)
    )
    lbar = bpy.context.active_object
    lbar.scale = (0.01, 0.01, H * 0.48)
    lbar.data.materials.append(make_emission(f"LWall_{i}", color, strength * 0.8))
    objects.append(lbar)

    # Right wall vertical bar
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=(W / 2 - 0.02, y, H / 2)
    )
    rbar = bpy.context.active_object
    rbar.scale = (0.01, 0.01, H * 0.48)
    rbar.data.materials.append(make_emission(f"RWall_{i}", color, strength * 0.8))
    objects.append(rbar)

print(f"Created corridor with {len(objects)} neon elements in {time.time()-t0:.1f}s")

# Camera — slightly off-center for asymmetric reflections
bpy.ops.object.camera_add(location=(0.2, 0.4, 1.5))
cam = bpy.context.active_object
bpy.context.scene.camera = cam
cam.data.lens = 24  # wide angle for dramatic perspective

bpy.ops.object.empty_add(location=(0, L, 1.6))
target = bpy.context.active_object
target.name = "CorridorEnd"
constraint = cam.constraints.new('TRACK_TO')
constraint.target = target
constraint.track_axis = 'TRACK_NEGATIVE_Z'
constraint.up_axis = 'UP_Y'

cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 5.0
cam.data.dof.aperture_fstop = 5.6

# World — pure black
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

# Render — high glossy bounces for deep mirror reflections
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = 512
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 64
scene.cycles.glossy_bounces = 56
scene.cycles.diffuse_bounces = 4
scene.cycles.transmission_bounces = 8
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

print(f"Rendering 1280x720 @ 512 samples (64 max bounces)...")
t_render = time.time()
bpy.ops.render.render(write_still=True)
t_render = time.time() - t_render

print(f"Done in {t_render:.1f}s ({os.path.getsize(OUTPUT):,} bytes)")
print(f"Output: {OUTPUT}")
