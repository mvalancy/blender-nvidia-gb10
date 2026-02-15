"""
Crystal Cave — procedural crystal formations with emission, refraction, and fog.
Showcases: Procedural geometry, volume absorption, point lights, glass + emission mix.
"""
import bpy
import bmesh
import math
import random
import time
import os

OUTPUT = "/tmp/blender_renders/crystal_cave.png"
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

random.seed(42)  # Reproducible


def clear():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def make_crystal_mat(name, color, emission_strength=0.0):
    """Glass + emission mix for glowing crystals."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new('ShaderNodeOutputMaterial')

    if emission_strength > 0:
        # Mix glass and emission
        mix = nodes.new('ShaderNodeMixShader')
        mix.inputs['Fac'].default_value = 0.45

        glass = nodes.new('ShaderNodeBsdfGlass')
        glass.inputs['Color'].default_value = (*color, 1)
        glass.inputs['IOR'].default_value = 1.8
        glass.inputs['Roughness'].default_value = 0.02

        emit = nodes.new('ShaderNodeEmission')
        emit.inputs['Color'].default_value = (*color, 1)
        emit.inputs['Strength'].default_value = emission_strength

        links.new(glass.outputs[0], mix.inputs[1])
        links.new(emit.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], out.inputs[0])
    else:
        glass = nodes.new('ShaderNodeBsdfGlass')
        glass.inputs['Color'].default_value = (*color, 1)
        glass.inputs['IOR'].default_value = 1.6
        glass.inputs['Roughness'].default_value = 0.01
        links.new(glass.outputs[0], out.inputs[0])

    return mat


def make_rock_mat(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = 0.15
    bsdf.inputs['Specular IOR Level'].default_value = 0.8

    # Add noise texture for bump
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 15
    noise.inputs['Detail'].default_value = 8
    noise.inputs['Roughness'].default_value = 0.7

    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.3

    links.new(noise.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs[0], bsdf.inputs['Normal'])
    links.new(bsdf.outputs[0], out.inputs[0])

    return mat


def create_crystal(location, height, radius, tilt, mat):
    """Create a hexagonal prism crystal with pointed tip."""
    verts = []
    faces = []
    n_sides = 6

    # Base hexagon
    for i in range(n_sides):
        angle = 2 * math.pi * i / n_sides
        verts.append((radius * math.cos(angle), radius * math.sin(angle), 0))

    # Top hexagon (slightly smaller)
    top_r = radius * 0.7
    for i in range(n_sides):
        angle = 2 * math.pi * i / n_sides
        verts.append((top_r * math.cos(angle), top_r * math.sin(angle), height * 0.75))

    # Tip
    verts.append((0, 0, height))

    # Side faces
    for i in range(n_sides):
        j = (i + 1) % n_sides
        faces.append((i, j, n_sides + j, n_sides + i))

    # Top faces (triangles to tip)
    tip = 2 * n_sides
    for i in range(n_sides):
        j = (i + 1) % n_sides
        faces.append((n_sides + i, n_sides + j, tip))

    # Bottom face
    faces.append(tuple(range(n_sides)))

    mesh = bpy.data.meshes.new("Crystal")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new("Crystal", mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (
        math.radians(tilt[0]),
        math.radians(tilt[1]),
        math.radians(random.uniform(0, 360))
    )
    obj.data.materials.append(mat)

    # Smooth shading on sides only
    for face in obj.data.polygons:
        face.use_smooth = True

    return obj


print("=" * 60)
print("CRYSTAL CAVE")
print("=" * 60)

clear()
t0 = time.time()

# Crystal materials
crystal_colors = [
    ("Amethyst", (0.6, 0.1, 0.9), 10.0),
    ("Citrine", (1.0, 0.8, 0.1), 8.0),
    ("Aquamarine", (0.1, 0.8, 1.0), 12.0),
    ("Rose Quartz", (1.0, 0.3, 0.5), 6.0),
    ("Clear Quartz", (0.85, 0.85, 0.95), 3.0),
    ("Emerald", (0.1, 0.9, 0.3), 9.0),
]
crystal_mats = [make_crystal_mat(n, c, e) for n, c, e in crystal_colors]

rock_mat = make_rock_mat("Cave Rock", (0.015, 0.012, 0.01))

# Floor — rocky ground
bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))
floor = bpy.context.active_object
floor.data.materials.append(rock_mat)

# Smooth dark floor — no displacement, reflects crystal colors cleanly

# No back wall — allows background to go to pure black

# Crystal clusters — groups growing from the ground and walls
crystals = []

# Ground cluster (center)
for i in range(20):
    angle = random.uniform(0, 2 * math.pi)
    r = random.uniform(0, 1.5)
    x = r * math.cos(angle)
    y = r * math.sin(angle)
    h = random.uniform(0.5, 2.5)
    rad = random.uniform(0.06, 0.18)
    tilt = (random.uniform(-15, 15), random.uniform(-15, 15))
    mat = crystal_mats[random.randint(0, len(crystal_mats) - 1)]
    crystals.append(create_crystal((x, y, 0), h, rad, tilt, mat))

# Side cluster (left)
for i in range(12):
    x = random.uniform(-3.5, -1.5)
    y = random.uniform(-1, 2)
    h = random.uniform(0.3, 1.5)
    rad = random.uniform(0.04, 0.12)
    tilt = (random.uniform(-20, 20), random.uniform(-20, 20))
    mat = crystal_mats[random.randint(0, len(crystal_mats) - 1)]
    crystals.append(create_crystal((x, y, 0), h, rad, tilt, mat))

# Ceiling stalactites (hanging down)
for i in range(10):
    x = random.uniform(-2, 2)
    y = random.uniform(-1, 3)
    h = random.uniform(0.5, 1.8)
    rad = random.uniform(0.05, 0.14)
    mat = crystal_mats[random.randint(0, len(crystal_mats) - 1)]
    obj = create_crystal((x, y, 5), h, rad, (180, 0), mat)
    crystals.append(obj)

print(f"Created {len(crystals)} crystals in {time.time()-t0:.1f}s")

# Point lights inside some crystals for inner glow
light_colors = [(0.5, 0.1, 1.0), (1.0, 0.8, 0.1), (0.1, 0.8, 1.0), (1.0, 0.3, 0.5)]
for i in range(4):
    c = crystals[i * 4]
    loc = (c.location.x, c.location.y, c.location.z + 0.5)
    bpy.ops.object.light_add(type='POINT', location=loc)
    light = bpy.context.active_object
    light.data.energy = 150
    light.data.color = light_colors[i]
    light.data.shadow_soft_size = 0.1

# Additional point lights deeper in the crystal cluster
for i in range(3):
    c = crystals[i * 6 + 2]
    loc = (c.location.x, c.location.y, c.location.z + 0.3)
    bpy.ops.object.light_add(type='POINT', location=loc)
    light = bpy.context.active_object
    light.data.energy = 80
    light.data.color = light_colors[(i + 2) % 4]
    light.data.shadow_soft_size = 0.08

# Strong key light — dramatic directional
bpy.ops.object.light_add(type='AREA', location=(3, -4, 4))
key = bpy.context.active_object
key.data.energy = 800
key.data.color = (1.0, 0.9, 0.75)
key.data.size = 1.5

# Cool fill from opposite side
bpy.ops.object.light_add(type='AREA', location=(-3, 3, 3))
fill = bpy.context.active_object
fill.data.energy = 300
fill.data.color = (0.3, 0.3, 0.9)
fill.data.size = 1.5

# Warm rim from behind — tighter to avoid flooding the background
bpy.ops.object.light_add(type='AREA', location=(0, 2, 1.5))
rim = bpy.context.active_object
rim.data.energy = 250
rim.data.color = (0.9, 0.4, 0.1)
rim.data.size = 0.8

# Camera
bpy.ops.object.camera_add(location=(3.0, -3.5, 2.0))
cam = bpy.context.active_object
bpy.context.scene.camera = cam
cam.data.lens = 35

bpy.ops.object.empty_add(location=(0, 0, 1.0))
target = bpy.context.active_object
target.name = "CaveTarget"
constraint = cam.constraints.new('TRACK_TO')
constraint.target = target
constraint.track_axis = 'TRACK_NEGATIVE_Z'
constraint.up_axis = 'UP_Y'

cam.data.dof.use_dof = True
cam.data.dof.focus_object = target
cam.data.dof.aperture_fstop = 3.5

# World — pure black background
world = bpy.data.worlds.new("CaveWorld")
bpy.context.scene.world = world
world.use_nodes = True
nodes = world.node_tree.nodes
links = world.node_tree.links
nodes.clear()

out = nodes.new('ShaderNodeOutputWorld')
bg = nodes.new('ShaderNodeBackground')
bg.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1)
bg.inputs['Strength'].default_value = 0.0
links.new(bg.outputs[0], out.inputs['Surface'])

# No fog — clean dark background for maximum contrast

# Render
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = 384
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 16
scene.cycles.transmission_bounces = 12
scene.cycles.volume_bounces = 4
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

print(f"Rendering 1280x720 @ 384 samples...")
t_render = time.time()
bpy.ops.render.render(write_still=True)
t_render = time.time() - t_render

print(f"Done in {t_render:.1f}s ({os.path.getsize(OUTPUT):,} bytes)")
print(f"Output: {OUTPUT}")
