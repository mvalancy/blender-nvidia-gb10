# Blender 5.0.1 on NVIDIA GB10 (DGX Spark)

Build Blender from source on **Linux ARM64** with full **CUDA GPU** support — one command, one hour.

```
$ blender --version
Blender 5.0.1

$ blender -b --python my_script.py   # headless rendering on GB10
```

## Why

There are no official Blender builds for Linux ARM64. Community efforts exist for CPU-only builds, but none support CUDA on the new NVIDIA GB10 (compute capability 12.1) with CUDA 13.

This repo provides a **fully automated, one-command build** that produces a feature-complete Blender with Cycles GPU rendering on the DGX Spark.

## Target System

| Component | Version |
|-----------|---------|
| Hardware | NVIDIA DGX Spark / GB10 |
| GPU Compute | SM 12.1 (Blackwell) |
| OS | Ubuntu 24.04 LTS (noble) |
| Arch | aarch64 (ARM64) |
| CUDA | 13.0+ |
| Driver | 580.x+ |
| GCC | 13.3 |

## Quick Start

```bash
git clone https://github.com/mvalancy/blender-nvidia-gb10.git
cd blender-nvidia-gb10
./setup.sh all    # ~1 hour total
blender --version
```

Or run individual steps:

```bash
./setup.sh deps        # Install system packages
./setup.sh clone       # Clone Blender v5.0.1
./setup.sh patch       # Apply ARM64 + CUDA 13 patches
./setup.sh build-deps  # Build 60+ third-party libs (~45 min)
./setup.sh build       # Build Blender (~10 min)
./setup.sh install     # Symlink to /usr/local/bin
```

Completed steps are checkpointed — re-running skips them automatically:

```bash
./setup.sh --status        # Show which steps are complete vs pending
./setup.sh --force build   # Re-run a step (ignoring checkpoint)
./setup.sh --clean         # Remove all checkpoints and build artifacts
./setup.sh --verbose all   # Show full build output instead of spinner
./setup.sh --help          # Full usage info
```

## Build Pipeline

```mermaid
flowchart TD
    A["`**setup.sh all**`"] --> B[deps]
    B --> C[clone]
    C --> D[patch]
    D --> E[build-deps]
    E --> F[build]
    F --> G[install]

    B -->|apt-get| B1[30+ system packages]
    B -->|symlink| B2[Ubuntu multiarch fix]
    B -->|touch| B3[CUDA 13 header stub]

    C -->|git clone| C1["Blender v5.0.1<br>from GitHub"]
    C -->|git lfs pull| C2["LFS data files<br>from projects.blender.org"]

    D -->|0001-0004| D1["lfdevs ARM64 patches<br>libffi, flex, USD, ROCm"]
    D -->|0005-0008| D2["GB10 + CUDA 13 patches<br>OIDN, libglu, Wayland, libdrm"]

    E -->|make deps| E1["~60 libraries built"]

    F -->|cmake + ninja| F1["Blender binary"]

    G -->|symlink| G1["installed to PATH"]

    style A fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style G1 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style D1 fill:#ffe0b2,stroke:#e65100,color:#bf360c
    style D2 fill:#ffe0b2,stroke:#e65100,color:#bf360c
```

## What Gets Patched (and Why)

Blender's build system assumes x86 Linux. Eight patches fix the ARM64 + CUDA 13 gaps:

```mermaid
flowchart LR
    subgraph lfdevs["Community ARM64 Patches"]
        P1["`**0001** libffi<br>GCC 14 missing decl`"]
        P2["`**0002** flex<br>GCC 14 segfault`"]
        P3["`**0003** USD<br>x86 Valgrind asm`"]
        P4["`**0004** ROCm<br>skip on aarch64`"]
    end

    subgraph gb10["CUDA 13 + Ubuntu 24.04 Patches"]
        P5["`**0005** OIDN<br>drop sm_70 Volta`"]
        P6["`**0006** libglu<br>libtool mismatch`"]
        P7["`**0007** Wayland+Mesa<br>lib64 to lib path`"]
        P8["`**0008** FFmpeg<br>link libdrm`"]
    end

    lfdevs --> gb10

    style lfdevs fill:#bbdefb,stroke:#0d47a1,color:#0d47a1
    style gb10 fill:#ffcdd2,stroke:#b71c1c,color:#b71c1c
```

### Patch Details

| # | File Modified | Problem | Fix |
|---|--------------|---------|-----|
| 0001 | `deps/cmake/libffi.cmake` | Missing declaration in libffi with GCC 14 | Add forward declaration |
| 0002 | `deps/cmake/flex.cmake` | flex segfaults via `reallocarray` on GCC 14 | Patch flex source |
| 0003 | `deps/cmake/usd.cmake` | USD includes x86 Valgrind assembly on Linux | Gate behind `__x86_64__` |
| 0004 | `deps/cmake/ispc.cmake` | ROCm packages are x86-only | Skip on `BLENDER_PLATFORM_ARM` |
| 0005 | `deps/cmake/openimagedenoise.cmake` | CUDA 13 dropped sm_70 (Volta) | Remove sm_70 targets at build time |
| 0006 | `deps/cmake/libglu.cmake` | libtool 2.4.6 vs 2.4.7 version mismatch | Run `autoreconf -fi` before configure |
| 0007 | `deps/cmake/wayland.cmake` + 4 more | Meson installs to `lib/` not `lib64/` on aarch64 | Conditional harvest paths |
| 0008 | `cmake/platform/platform_unix.cmake` | FFmpeg kmsgrab needs libdrm symbols | Add `find_library(DRM_LIBRARY drm)` |

### Additional System Workarounds

These are handled automatically by `setup.sh deps`:

| Issue | Cause | Fix |
|-------|-------|-----|
| ISPC can't find `bits/wordsize.h` | Ubuntu multiarch puts headers in `/usr/include/aarch64-linux-gnu/` | Symlink `bits`, `gnu`, `asm` to `/usr/include/` |
| Clang errors on `texture_fetch_functions.h` | CUDA 13 removed this header; Clang's wrapper still includes it | Create empty stub file |
| Blender segfaults on startup | Git LFS pointers instead of real data files (131 bytes vs 1MB+) | Pull LFS from `projects.blender.org` |

## Architecture

```mermaid
graph TB
    subgraph build["Build Output"]
        BIN["blender binary"]
        LIBS["60+ prebuilt libraries"]
    end

    subgraph runtime["Runtime Stack"]
        CYCLES["Cycles Renderer"]
        EEVEE["EEVEE"]
        PYTHON["Python 3.11"]
    end

    subgraph hardware["NVIDIA DGX Spark"]
        GPU["GB10 GPU<br>SM 12.1, CUDA 13"]
        CPU["Grace CPU<br>20 ARM cores"]
        RAM["120 GB<br>Unified Memory"]
    end

    BIN --> CYCLES
    BIN --> EEVEE
    BIN --> PYTHON
    CYCLES -->|CUDA| GPU
    CYCLES -->|threads| CPU
    EEVEE -->|Vulkan| GPU
    PYTHON -->|bpy API| BIN
    LIBS --> BIN

    style GPU fill:#76b900,stroke:#333,color:#fff,font-weight:bold
    style BIN fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
```

## Headless / AI Usage

The primary use case is running Blender headlessly for automated 3D workflows:

```bash
# Render a scene on the GPU
blender -b scene.blend -o //output_ -F PNG -f 1 -- --cycles-device CUDA

# Run a Python script
blender -b --factory-startup --python my_pipeline.py

# Detect GPU from Python
blender -b --factory-startup --python-expr "
import bpy
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.get_devices()
for d in prefs.get_devices_for_type('CUDA'):
    print(f'{d.name} (use={d.use})')
"
# Output: NVIDIA GB10 (use=True)
```

## Verification

After building, run the included test:

```bash
blender -b --factory-startup --python test_blender.py
```

Expected output:
```
Blender 5.0.1
  [CUDA] NVIDIA GB10 (use=True)
  Cycles GPU render: PASS
  Cycles CPU render: PASS
  Python API: PASS
  File I/O: PASS
```

## Benchmark

The included `benchmark.py` creates a procedural Menger sponge fractal (400 glass/metal cubes) with volumetric lighting, then renders at multiple resolutions on the GPU:

```bash
blender -b --factory-startup --python benchmark.py
```

Results on NVIDIA GB10:

| Resolution | Samples | Time |
|-----------|---------|------|
| 480x270 | 16 | 1.6s |
| 1280x720 | 64 | 9.3s |
| 1920x1080 | 128 | 24.9s |

![Benchmark render](images/benchmark_render.png)

*Menger sponge fractal — glass BSDF, metal BSDF, emission, volumetric scatter — rendered on the GB10 via Cycles CUDA.*

## Gallery

All renders generated headlessly on the GB10 via `blender -b --factory-startup --python <script>`. Source scripts in [`renders/`](renders/).

| | |
|:---:|:---:|
| [![Golden Spiral](images/thumb_golden_spiral.png)](images/golden_spiral.png) | [![Glass Fractal](images/thumb_glass_fractal.png)](images/glass_fractal.png) |
| **Golden Fibonacci Spiral** — 300 metallic + SSS spheres, 384 samples | **Glass Sierpinski Tetrahedron** — 256 emissive glass tetrahedra, 512 samples |
| [![Crystal Cave](images/thumb_crystal_cave.png)](images/crystal_cave.png) | [![Infinite Mirrors](images/thumb_infinite_mirrors.png)](images/infinite_mirrors.png) |
| **Crystal Cave** — 42 hexagonal crystals on polished obsidian, 384 samples | **Infinite Mirror Corridor** — 64-bounce neon reflections, 512 samples |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BLENDER_BUILD_DIR` | `~/blender-gb10-build` | Override the build/source/checkpoint directory |
| `NO_COLOR` | *(unset)* | Disable colored output (also auto-disabled when piped) |

```bash
export BLENDER_BUILD_DIR=/path/to/build
./setup.sh all
```

## Disk & Time Requirements

| Resource | Requirement |
|----------|-------------|
| Disk space | ~50 GB (source + deps + build) |
| Build time (deps) | ~45 minutes |
| Build time (Blender) | ~10 minutes |
| RAM | 8 GB minimum, 16+ GB recommended |
| Internet | ~5 GB download (source + deps) |

## Credits

- [lfdevs/blender-linux-arm64](https://github.com/lfdevs/blender-linux-arm64) — Community ARM64 CI builds and patches 0001-0004
- [CoconutMacaroon/blender-arm64](https://github.com/CoconutMacaroon/blender-arm64) — DGX Spark build reference
- [Blender Developer Forum](https://devtalk.blender.org/t/linux-aarch64-source-build/35311) — Community build guidance
- [Blender](https://www.blender.org/) — The amazing open-source 3D suite

## License

The patches in this repository are provided under the same license as Blender ([GPL-3.0](https://www.gnu.org/licenses/gpl-3.0.en.html)). Blender itself is not included — it is cloned from the official repository during the build.
