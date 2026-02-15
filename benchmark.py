"""
GB10 Benchmark: Procedural fractal scene with glass, metal, and volumetric lighting.
Run: blender -b --factory-startup --python benchmark.py

Creates a Menger sponge fractal made of glass/metal cubes, lit by area lights
with volumetric scattering, and renders at 1920x1080 on the GPU.
"""
import bpy
import bmesh
import math
import time
import os
import sys

OUTPUT_DIR = "/tmp/blender_benchmark"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for col in bpy.data.collections:
        bpy.data.collections.remove(col)


def make_glass_material(name, color, roughness=0.05):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputMaterial')
    glass = nodes.new('ShaderNodeBsdfGlass')
    glass.inputs['Color'].default_value = (*color, 1.0)
    glass.inputs['Roughness'].default_value = roughness
    glass.inputs['IOR'].default_value = 1.45
    links.new(glass.outputs['BSDF'], output.inputs['Surface'])
    return mat


def make_metal_material(name, color, roughness=0.15):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputMaterial')
    principled = nodes.new('ShaderNodeBsdfPrincipled')
    principled.inputs['Base Color'].default_value = (*color, 1.0)
    principled.inputs['Metallic'].default_value = 1.0
    principled.inputs['Roughness'].default_value = roughness
    links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    return mat


def make_emission_material(name, color, strength=10.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputMaterial')
    emit = nodes.new('ShaderNodeEmission')
    emit.inputs['Color'].default_value = (*color, 1.0)
    emit.inputs['Strength'].default_value = strength
    links.new(emit.outputs['Emission'], output.inputs['Surface'])
    return mat


def menger_sponge(center, size, depth, collection, materials):
    """Recursively create a Menger sponge fractal."""
    if depth == 0:
        bpy.ops.mesh.primitive_cube_add(size=size, location=center)
        obj = bpy.context.active_object

        # Assign material based on position hash for visual variety
        idx = int(abs(center[0] * 7 + center[1] * 13 + center[2] * 19)) % len(materials)
        obj.data.materials.append(materials[idx])

        # Move to collection
        for col in obj.users_collection:
            col.objects.unlink(obj)
        collection.objects.link(obj)
        return [obj]

    objects = []
    step = size / 3.0
    for x in range(-1, 2):
        for y in range(-1, 2):
            for z in range(-1, 2):
                # Skip center cross (the holes that make it a Menger sponge)
                axes_at_zero = (x == 0) + (y == 0) + (z == 0)
                if axes_at_zero >= 2:
                    continue

                new_center = (
                    center[0] + x * step,
                    center[1] + y * step,
                    center[2] + z * step,
                )
                objects.extend(
                    menger_sponge(new_center, step, depth - 1, collection, materials)
                )
    return objects


def setup_scene():
    clear_scene()

    # Create materials
    glass_blue = make_glass_material("Glass Blue", (0.2, 0.4, 0.9), roughness=0.02)
    glass_amber = make_glass_material("Glass Amber", (0.9, 0.6, 0.1), roughness=0.05)
    metal_gold = make_metal_material("Metal Gold", (0.95, 0.75, 0.2), roughness=0.1)
    metal_chrome = make_metal_material("Metal Chrome", (0.8, 0.8, 0.85), roughness=0.05)
    materials = [glass_blue, glass_amber, metal_gold, metal_chrome]

    # Create fractal collection
    fractal_col = bpy.data.collections.new("Menger Sponge")
    bpy.context.scene.collection.children.link(fractal_col)

    # Build Menger sponge (depth 2 = 400 cubes, good GPU workout)
    print("Building Menger sponge (depth 2)...")
    t0 = time.time()
    objects = menger_sponge((0, 0, 0), 3.0, 2, fractal_col, materials)
    print(f"  Created {len(objects)} cubes in {time.time() - t0:.1f}s")

    # Ground plane (dark mirror)
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, -1.8))
    ground = bpy.context.active_object
    ground.name = "Ground"
    ground_mat = make_metal_material("Ground Mirror", (0.02, 0.02, 0.03), roughness=0.02)
    ground.data.materials.append(ground_mat)

    # Emissive sphere (light source inside the fractal)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.15, location=(0, 0, 0))
    emitter = bpy.context.active_object
    emitter.name = "Core Light"
    emit_mat = make_emission_material("Core Emission", (1.0, 0.8, 0.4), strength=50.0)
    emitter.data.materials.append(emit_mat)

    # Area lights
    for i, (pos, color, energy) in enumerate([
        ((4, -3, 4), (0.8, 0.9, 1.0), 200),   # Key light (cool white)
        ((-3, 4, 3), (1.0, 0.7, 0.3), 100),    # Fill (warm)
        ((0, -5, 1), (0.4, 0.5, 1.0), 80),     # Rim (blue)
    ]):
        bpy.ops.object.light_add(type='AREA', location=pos)
        light = bpy.context.active_object
        light.name = f"Area Light {i+1}"
        light.data.energy = energy
        light.data.color = color
        light.data.size = 2.0
        # Point at origin
        direction = mathutils_look_at(pos, (0, 0, 0))
        light.rotation_euler = direction

    # Camera
    bpy.ops.object.camera_add(location=(4.5, -4.5, 3.5))
    cam = bpy.context.active_object
    cam.name = "Benchmark Camera"
    cam.rotation_euler = (math.radians(60), 0, math.radians(45))
    bpy.context.scene.camera = cam

    # Point camera at fractal
    constraint = cam.constraints.new('TRACK_TO')
    constraint.target = emitter
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'

    return len(objects)


def mathutils_look_at(source, target):
    """Calculate rotation to point from source toward target."""
    dx = target[0] - source[0]
    dy = target[1] - source[1]
    dz = target[2] - source[2]
    dist_xy = math.sqrt(dx*dx + dy*dy)
    rot_x = math.atan2(-dz, dist_xy)
    rot_z = math.atan2(dy, dx) - math.pi/2
    return (rot_x + math.pi/2, 0, rot_z)


def configure_render(samples=128, resolution=(1920, 1080)):
    scene = bpy.context.scene

    # Cycles GPU
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True

    # Enable GPU
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True

    # Resolution
    scene.render.resolution_x = resolution[0]
    scene.render.resolution_y = resolution[1]
    scene.render.resolution_percentage = 100

    # Film
    scene.render.film_transparent = False

    # World (dark with slight volumetric fog)
    if bpy.data.worlds.get("Benchmark World"):
        world = bpy.data.worlds["Benchmark World"]
    else:
        world = bpy.data.worlds.new("Benchmark World")
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputWorld')

    # Dark blue background
    bg = nodes.new('ShaderNodeBackground')
    bg.inputs['Color'].default_value = (0.01, 0.01, 0.03, 1.0)
    bg.inputs['Strength'].default_value = 0.5

    # Volume scatter for light rays
    vol_scatter = nodes.new('ShaderNodeVolumeScatter')
    vol_scatter.inputs['Color'].default_value = (0.8, 0.85, 1.0, 1.0)
    vol_scatter.inputs['Density'].default_value = 0.02

    links.new(bg.outputs['Background'], output.inputs['Surface'])
    links.new(vol_scatter.outputs['Volume'], output.inputs['Volume'])

    # Output settings
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_depth = '16'


def run_benchmark():
    print("=" * 60)
    print("GB10 BLENDER BENCHMARK")
    print(f"Blender {bpy.app.version_string}")
    print("=" * 60)

    # Setup
    print("\n--- Scene Setup ---")
    t_setup = time.time()
    num_objects = setup_scene()
    t_setup = time.time() - t_setup
    print(f"  Scene setup: {t_setup:.1f}s ({num_objects} fractal cubes)")

    # Configure
    print("\n--- Render Settings ---")

    # Low-res preview first
    print("\n  [1/3] Preview render (480x270, 16 samples)...")
    configure_render(samples=16, resolution=(480, 270))
    scene = bpy.context.scene
    scene.render.filepath = os.path.join(OUTPUT_DIR, "benchmark_preview.png")
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    t_preview = time.time() - t0
    print(f"        Done in {t_preview:.1f}s")

    # Medium render
    print("\n  [2/3] Medium render (1280x720, 64 samples)...")
    configure_render(samples=64, resolution=(1280, 720))
    scene.render.filepath = os.path.join(OUTPUT_DIR, "benchmark_720p.png")
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    t_720 = time.time() - t0
    print(f"        Done in {t_720:.1f}s")

    # Full render
    print("\n  [3/3] Full render (1920x1080, 128 samples)...")
    configure_render(samples=128, resolution=(1920, 1080))
    scene.render.filepath = os.path.join(OUTPUT_DIR, "benchmark_1080p.png")
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    t_1080 = time.time() - t0
    print(f"        Done in {t_1080:.1f}s")

    # Results
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Scene: Menger sponge ({num_objects} glass/metal cubes)")
    print(f"  Features: Glass BSDF, Metal BSDF, Emission, Volumetric scatter")
    print(f"  GPU: CUDA (via Cycles)")
    print()
    print(f"  Preview  (480x270,  16 smp): {t_preview:6.1f}s")
    print(f"  Medium   (1280x720, 64 smp): {t_720:6.1f}s")
    print(f"  Full     (1920x1080,128 smp): {t_1080:6.1f}s")
    print()

    for f in ["benchmark_preview.png", "benchmark_720p.png", "benchmark_1080p.png"]:
        path = os.path.join(OUTPUT_DIR, f)
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"  {f}: {size:,} bytes")

    # Save .blend file too
    blend_path = os.path.join(OUTPUT_DIR, "benchmark_scene.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"\n  Scene saved: {blend_path}")
    print("=" * 60)


if __name__ == "__main__":
    run_benchmark()
