"""
Blender Build Verification Test
Run: blender -b --factory-startup --python test_blender.py
"""
import bpy
import sys
import os

PASS = 0
FAIL = 0


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        status = "PASS"
    else:
        FAIL += 1
        status = "FAIL"
    suffix = f" ({detail})" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    return condition


print("=" * 60)
print(f"Blender {bpy.app.version_string}")
print(f"Build: {bpy.app.build_date.decode()} {bpy.app.build_time.decode()}")
print(f"Platform: {bpy.app.build_platform.decode()}")
print(f"Python: {sys.version.split()[0]}")
print("=" * 60)

# --- Version ---
print("\n--- Version ---")
test("Blender version", bpy.app.version >= (5, 0, 0), bpy.app.version_string)

# --- GPU Detection ---
print("\n--- CUDA GPU Detection ---")
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.get_devices()
    cuda_devices = prefs.get_devices_for_type('CUDA')
    gpu_names = [d.name for d in cuda_devices if d.name != ""]
    test("CUDA devices found", len(gpu_names) > 0, ", ".join(gpu_names))
    for d in cuda_devices:
        if d.name and "CPU" not in d.name:
            print(f"       {d.name} (use={d.use})")
except Exception as e:
    test("CUDA detection", False, str(e))

# --- Cycles GPU Render ---
print("\n--- Cycles GPU Render (64x64, 4 samples) ---")
try:
    scene = bpy.context.scene
    scene.render.resolution_x = 64
    scene.render.resolution_y = 64
    scene.render.resolution_percentage = 100
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = 4
    outpath = '/tmp/blender_test_gpu.png'
    scene.render.filepath = outpath
    bpy.ops.render.render(write_still=True)
    exists = os.path.exists(outpath)
    size = os.path.getsize(outpath) if exists else 0
    test("Cycles GPU render", exists and size > 0, f"{size} bytes")
except Exception as e:
    test("Cycles GPU render", False, str(e))

# --- Cycles CPU Render ---
print("\n--- Cycles CPU Render (64x64, 4 samples) ---")
try:
    scene.cycles.device = 'CPU'
    outpath = '/tmp/blender_test_cpu.png'
    scene.render.filepath = outpath
    bpy.ops.render.render(write_still=True)
    exists = os.path.exists(outpath)
    size = os.path.getsize(outpath) if exists else 0
    test("Cycles CPU render", exists and size > 0, f"{size} bytes")
except Exception as e:
    test("Cycles CPU render", False, str(e))

# --- Python API ---
print("\n--- Python API ---")
try:
    bpy.ops.mesh.primitive_monkey_add()
    obj = bpy.context.active_object
    test("Add mesh (Suzanne)", obj is not None, obj.name)

    bpy.ops.object.modifier_add(type='SUBSURF')
    test("Add modifier", len(obj.modifiers) > 0, obj.modifiers[0].name)

    mat = bpy.data.materials.new('TestMat')
    mat.use_nodes = True
    obj.data.materials.append(mat)
    test("Material + nodes", mat.node_tree is not None, mat.name)
except Exception as e:
    test("Python API", False, str(e))

# --- File I/O ---
print("\n--- File I/O ---")
try:
    outpath = '/tmp/blender_test_export.obj'
    bpy.ops.wm.obj_export(filepath=outpath)
    exists = os.path.exists(outpath)
    size = os.path.getsize(outpath) if exists else 0
    test("OBJ export", exists and size > 0, f"{size} bytes")
except Exception as e:
    test("OBJ export", False, str(e))

try:
    outpath = '/tmp/blender_test.blend'
    bpy.ops.wm.save_as_mainfile(filepath=outpath)
    exists = os.path.exists(outpath)
    size = os.path.getsize(outpath) if exists else 0
    test(".blend save", exists and size > 0, f"{size} bytes")
except Exception as e:
    test(".blend save", False, str(e))

# --- Geometry Nodes ---
print("\n--- Geometry Nodes ---")
try:
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    mod = cube.modifiers.new("GeometryNodes", 'NODES')
    group = bpy.data.node_groups.new("TestGeoNodes", 'GeometryNodeTree')
    mod.node_group = group
    test("Geometry nodes", mod.node_group is not None, group.name)
except Exception as e:
    test("Geometry nodes", False, str(e))

# --- Compositor ---
print("\n--- Compositor ---")
try:
    tree = bpy.data.node_groups.new("TestCompositor", 'CompositorNodeTree')
    blur = tree.nodes.new('CompositorNodeBlur')
    test("Compositor node", blur is not None, blur.name)
except Exception as e:
    test("Compositor", False, str(e))

# --- Summary ---
total = PASS + FAIL
print("\n" + "=" * 60)
print(f"Results: {PASS}/{total} passed", end="")
if FAIL > 0:
    print(f", {FAIL} FAILED")
else:
    print(" - ALL TESTS PASSED")
print("=" * 60)

if FAIL > 0:
    sys.exit(1)
