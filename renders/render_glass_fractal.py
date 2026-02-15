"""
Glass Sierpinski Tetrahedron — recursive fractal with caustics and colored glass.
Showcases: Glass BSDF, caustics, area lighting, depth of field, denoising.
"""
import bpy
import bmesh
import math
import time
import os

OUTPUT = "/tmp/blender_renders/glass_fractal.png"
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)


def clear():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def make_glass(name, color, ior=1.5, roughness=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    glass = nodes.new('ShaderNodeBsdfGlass')
    glass.inputs['Color'].default_value = (*color, 1)
    glass.inputs['IOR'].default_value = ior
    glass.inputs['Roughness'].default_value = roughness
    links.new(glass.outputs[0], out.inputs[0])
    return mat


def make_principled(name, color, metallic=0.0, roughness=0.5, emission_color=None, emission_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    if emission_color:
        bsdf.inputs['Emission Color'].default_value = (*emission_color, 1)
        bsdf.inputs['Emission Strength'].default_value = emission_strength
    links.new(bsdf.outputs[0], out.inputs[0])
    return mat


def tetrahedron_verts(center, size):
    """Return 4 vertices of a regular tetrahedron."""
    cx, cy, cz = center
    s = size
    # Regular tetrahedron vertices
    return [
        (cx, cy, cz + s * 0.612),
        (cx + s * 0.5, cy - s * 0.289, cz - s * 0.204),
        (cx - s * 0.5, cy - s * 0.289, cz - s * 0.204),
        (cx, cy + s * 0.577, cz - s * 0.204),
    ]


def create_tetrahedron(center, size, mat):
    """Create a single tetrahedron mesh object."""
    verts = tetrahedron_verts(center, size)
    faces = [(0, 1, 2), (0, 2, 3), (0, 3, 1), (1, 3, 2)]

    mesh = bpy.data.meshes.new("Tet")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new("Tet", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)

    # Smooth shading
    for face in obj.data.polygons:
        face.use_smooth = True

    return obj


def sierpinski(center, size, depth, materials, objects):
    """Recursively build a Sierpinski tetrahedron."""
    if depth == 0:
        mat = materials[len(objects) % len(materials)]
        obj = create_tetrahedron(center, size, mat)
        objects.append(obj)
        return

    verts = tetrahedron_verts(center, size)
    half = size / 2.0
    for v in verts:
        mid = ((center[0] + v[0]) / 2, (center[1] + v[1]) / 2, (center[2] + v[2]) / 2)
        sierpinski(mid, half, depth - 1, materials, objects)


def setup_world():
    world = bpy.data.worlds.new("FractalWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()

    out = nodes.new('ShaderNodeOutputWorld')
    bg = nodes.new('ShaderNodeBackground')
    bg.inputs['Color'].default_value = (0.005, 0.005, 0.015, 1)
    bg.inputs['Strength'].default_value = 0.3
    links.new(bg.outputs[0], out.inputs['Surface'])

    # Subtle volume for light rays
    vol = nodes.new('ShaderNodeVolumeScatter')
    vol.inputs['Color'].default_value = (0.7, 0.8, 1.0, 1)
    vol.inputs['Density'].default_value = 0.008
    links.new(vol.outputs[0], out.inputs['Volume'])


print("=" * 60)
print("GLASS SIERPINSKI TETRAHEDRON")
print("=" * 60)

clear()
t0 = time.time()

# Materials — different colored glass for each level
materials = [
    make_glass("Ruby Glass", (0.9, 0.1, 0.15), ior=1.52),
    make_glass("Sapphire Glass", (0.1, 0.2, 0.9), ior=1.77),
    make_glass("Emerald Glass", (0.05, 0.8, 0.2), ior=1.58),
    make_glass("Amber Glass", (0.95, 0.7, 0.1), ior=1.54),
]

# Build fractal (depth 4 = 256 tetrahedra)
objects = []
sierpinski((0, 0, 0), 3.0, 4, materials, objects)
print(f"Created {len(objects)} tetrahedra in {time.time()-t0:.1f}s")

# Ground — dark reflective
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, -1.0))
ground = bpy.context.active_object
ground.data.materials.append(
    make_principled("Dark Mirror", (0.01, 0.01, 0.02), metallic=1.0, roughness=0.03)
)

# Lighting — three colored area lights + one key
for pos, color, energy, size in [
    ((5, -4, 6), (1.0, 0.95, 0.9), 400, 3),      # Key warm white
    ((-4, 5, 4), (0.3, 0.5, 1.0), 200, 2),         # Fill cool blue
    ((0, -6, 2), (1.0, 0.3, 0.1), 150, 1.5),       # Rim warm orange
    ((0, 0, 8), (1.0, 1.0, 1.0), 100, 4),           # Top soft
]:
    bpy.ops.object.light_add(type='AREA', location=pos)
    light = bpy.context.active_object
    light.data.energy = energy
    light.data.color = color
    light.data.size = size
    # Point at center
    constraint = light.constraints.new('TRACK_TO')
    empty = bpy.data.objects.get("Target")
    if not empty:
        bpy.ops.object.empty_add(location=(0, 0, 0.3))
        empty = bpy.context.active_object
        empty.name = "Target"
    constraint.target = empty
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'

# Camera
bpy.ops.object.camera_add(location=(5.5, -5.0, 4.0))
cam = bpy.context.active_object
bpy.context.scene.camera = cam
constraint = cam.constraints.new('TRACK_TO')
constraint.target = empty
constraint.track_axis = 'TRACK_NEGATIVE_Z'
constraint.up_axis = 'UP_Y'

# Depth of field
cam.data.dof.use_dof = True
cam.data.dof.focus_object = empty
cam.data.dof.aperture_fstop = 4.0

setup_world()

# Render settings
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = 512
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 16
scene.cycles.glossy_bounces = 8
scene.cycles.transmission_bounces = 12
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_depth = '16'

# GPU setup
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'CUDA'
prefs.get_devices()
for d in prefs.devices:
    d.use = True

scene.render.filepath = OUTPUT

print(f"Rendering 1280x720 @ 512 samples...")
t_render = time.time()
bpy.ops.render.render(write_still=True)
t_render = time.time() - t_render

size = os.path.getsize(OUTPUT)
print(f"Done in {t_render:.1f}s ({size:,} bytes)")
print(f"Output: {OUTPUT}")
