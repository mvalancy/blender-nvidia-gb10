"""
Golden Spiral — metallic spheres arranged in a Fibonacci spiral with subsurface scattering.
Showcases: SSS materials, metallic shaders, HDRI-like lighting, motion blur, volumetrics.
"""
import bpy
import math
import time
import os

OUTPUT = "/tmp/blender_renders/golden_spiral.png"
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)


def clear():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def make_principled(name, color, metallic=0.0, roughness=0.5, subsurface=0.0, ss_radius=None):
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
    if subsurface > 0:
        bsdf.inputs['Subsurface Weight'].default_value = subsurface
        bsdf.inputs['Subsurface Scale'].default_value = 0.1
        if ss_radius:
            bsdf.inputs['Subsurface Radius'].default_value = ss_radius
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
print("GOLDEN FIBONACCI SPIRAL")
print("=" * 60)

clear()
t0 = time.time()

golden_angle = math.pi * (3 - math.sqrt(5))  # ~137.5 degrees

# Materials
mat_gold = make_principled("Gold", (0.95, 0.75, 0.15), metallic=1.0, roughness=0.08)
mat_copper = make_principled("Copper", (0.85, 0.45, 0.2), metallic=1.0, roughness=0.12)
mat_bronze = make_principled("Bronze", (0.7, 0.45, 0.2), metallic=1.0, roughness=0.15)
mat_jade = make_principled("Jade", (0.15, 0.6, 0.3), metallic=0.0, roughness=0.2,
                            subsurface=0.6, ss_radius=(0.1, 0.8, 0.2))
mat_rosegold = make_principled("RoseGold", (0.85, 0.5, 0.45), metallic=1.0, roughness=0.1)
materials = [mat_gold, mat_copper, mat_bronze, mat_jade, mat_rosegold]

# Create spiral of spheres
n_spheres = 300
objects = []
for i in range(n_spheres):
    theta = i * golden_angle
    r = 0.15 * math.sqrt(i)
    x = r * math.cos(theta)
    y = r * math.sin(theta)

    # Size varies — larger in center, smaller outward
    sphere_size = 0.08 + 0.06 * (1 - i / n_spheres)
    z = sphere_size  # sit on ground plane

    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=sphere_size, segments=24, ring_count=16, location=(x, y, z)
    )
    obj = bpy.context.active_object
    obj.data.materials.append(materials[i % len(materials)])

    # Smooth shading
    bpy.ops.object.shade_smooth()
    objects.append(obj)

print(f"Created {len(objects)} spheres in {time.time()-t0:.1f}s")

# Small emissive accents tucked among the spheres (not floating white blobs)
for i in range(8):
    angle = i * golden_angle * 30
    r = 0.15 * math.sqrt(i * 35)
    x = r * math.cos(angle)
    y = r * math.sin(angle)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.03, location=(x, y, 0.15))
    orb = bpy.context.active_object
    colors = [(1, 0.6, 0.1), (0.1, 0.6, 1), (1, 0.2, 0.4), (0.2, 1, 0.4),
              (0.7, 0.2, 1), (1, 0.4, 0.05), (0.05, 0.8, 0.8), (1, 0.1, 0.5)]
    orb.data.materials.append(make_emission(f"Orb{i}", colors[i], 15))
    bpy.ops.object.shade_smooth()

# Ground plane
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
ground = bpy.context.active_object
ground.data.materials.append(
    make_principled("Ground", (0.02, 0.02, 0.025), metallic=1.0, roughness=0.05)
)

# Lighting — dramatic three-point setup
bpy.ops.object.light_add(type='AREA', location=(4, -3, 5))
key = bpy.context.active_object
key.data.energy = 1200
key.data.color = (1.0, 0.9, 0.75)
key.data.size = 2.0

bpy.ops.object.light_add(type='AREA', location=(-3, 4, 3))
fill = bpy.context.active_object
fill.data.energy = 350
fill.data.color = (0.3, 0.4, 1.0)
fill.data.size = 1.8

bpy.ops.object.light_add(type='AREA', location=(0, -4, 1.5))
rim = bpy.context.active_object
rim.data.energy = 450
rim.data.color = (1.0, 0.5, 0.15)
rim.data.size = 1.2

# Camera — looking down at an angle
bpy.ops.object.camera_add(location=(3.5, -3.5, 3.2))
cam = bpy.context.active_object
bpy.context.scene.camera = cam

# Track to center
bpy.ops.object.empty_add(location=(0, 0, 0.3))
target = bpy.context.active_object
target.name = "SpiralTarget"
constraint = cam.constraints.new('TRACK_TO')
constraint.target = target
constraint.track_axis = 'TRACK_NEGATIVE_Z'
constraint.up_axis = 'UP_Y'

# DOF
cam.data.dof.use_dof = True
cam.data.dof.focus_object = target
cam.data.dof.aperture_fstop = 2.8
cam.data.lens = 50

# World — pure black, no volumetrics (clean black background)
world = bpy.data.worlds.new("SpiralWorld")
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

# Render
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = 384
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 12
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
