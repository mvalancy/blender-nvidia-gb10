#!/usr/bin/env bash
# ===========================================================================
# Blender 5.0.1 Build Script for NVIDIA DGX Spark / GB10
# Ubuntu 24.04 LTS (aarch64) + CUDA 13
# ===========================================================================
# Usage: ./setup.sh [step]
#   Steps: deps, clone, patch, build-deps, build, install, all
#   Default: all (runs everything)
#
# Tested on:
#   - NVIDIA DGX Spark / GB10 (compute capability 12.1)
#   - Ubuntu 24.04 LTS (noble) aarch64
#   - CUDA 13.0, Driver 580.x
#   - GCC 13.3, 20 cores, 120GB RAM
#
# Total build time: ~1 hour (45 min deps + 10 min Blender)
# ===========================================================================

set -euo pipefail

BLENDER_VERSION="5.0.1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${BLENDER_BUILD_DIR:-$HOME/blender-gb10-build}"
BLENDER_SRC="$PROJECT_DIR/blender"
BUILD_DIR="$PROJECT_DIR/build_linux_release"
LIBDIR="$BLENDER_SRC/lib/linux_arm64"
PATCH_DIR="$SCRIPT_DIR/patches"
LOG_FILE="$PROJECT_DIR/build.log"

step="${1:-all}"

# ---------------------------------------------------------------------------
# Step 1: Install system dependencies
# ---------------------------------------------------------------------------
install_deps() {
    echo "=== [1/6] Installing system dependencies ==="
    sudo apt-get update -qq

    sudo apt-get install -y \
        build-essential git git-lfs cmake ninja-build ccache \
        patch autoconf automake libtool autopoint \
        bison flex gettext texinfo help2man yasm wget patchelf meson \
        python3-dev python3-mako python3-yaml \
        libx11-dev libxxf86vm-dev libxcursor-dev libxi-dev libxrandr-dev \
        libxinerama-dev libxkbcommon-dev libxkbcommon-x11-dev libxshmfence-dev \
        libwayland-dev libdecor-0-dev wayland-protocols \
        libdbus-1-dev libgl-dev libegl-dev mesa-common-dev libglu1-mesa-dev libxt-dev \
        libdrm-dev libgbm-dev libudev-dev libinput-dev libevdev-dev \
        libasound2-dev libpulse-dev libjack-jackd2-dev \
        zlib1g-dev libncurses-dev libexpat1-dev \
        libcairo2-dev libpixman-1-dev libffi-dev \
        tcl perl libxml2-dev \
        libxcb-randr0-dev libxcb-dri2-0-dev libxcb-dri3-dev \
        libxcb-present-dev libxcb-sync-dev libxcb-glx0-dev \
        libxcb-shm0-dev libxcb-xfixes0-dev libx11-xcb-dev \
        libgles2-mesa-dev

    # Ubuntu multiarch: the LLVM/Clang built by make deps can't find
    # headers in /usr/include/aarch64-linux-gnu/. ISPC needs them.
    for dir in bits gnu asm; do
        if [ ! -e "/usr/include/$dir" ] && [ -d "/usr/include/aarch64-linux-gnu/$dir" ]; then
            echo "Symlinking /usr/include/$dir"
            sudo ln -sf "/usr/include/aarch64-linux-gnu/$dir" "/usr/include/$dir"
        fi
    done

    # CUDA 13 removed texture_fetch_functions.h but Clang still references it
    if [ -d /usr/local/cuda ] && [ ! -f /usr/local/cuda/include/texture_fetch_functions.h ]; then
        echo "Creating stub texture_fetch_functions.h for CUDA 13"
        sudo touch /usr/local/cuda/include/texture_fetch_functions.h
    fi

    echo "=== Dependencies installed ==="
}

# ---------------------------------------------------------------------------
# Step 2: Clone Blender source
# ---------------------------------------------------------------------------
clone_source() {
    echo "=== [2/6] Cloning Blender v${BLENDER_VERSION} ==="
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"

    if [ ! -d "$BLENDER_SRC" ]; then
        GIT_LFS_SKIP_SMUDGE=1 git clone \
            -b "v${BLENDER_VERSION}" --depth 1 \
            https://github.com/blender/blender.git

        # GitHub doesn't host Blender's LFS objects
        cd "$BLENDER_SRC"
        git config lfs.url https://projects.blender.org/blender/blender.git/info/lfs
        git lfs pull --include="release/datafiles/*"
        cd "$PROJECT_DIR"
    else
        echo "Source already exists, skipping."
    fi
}

# ---------------------------------------------------------------------------
# Step 3: Apply patches
# ---------------------------------------------------------------------------
apply_patches() {
    echo "=== [3/6] Applying patches ==="
    cd "$BLENDER_SRC"

    git config user.email "builder@local"
    git config user.name "Builder"

    if git log --oneline | grep -q "GB10 patches"; then
        echo "Patches already applied, skipping."
        return
    fi

    # Apply all patches in order
    for p in $(ls -1 "$PATCH_DIR"/*.patch 2>/dev/null | sort); do
        echo "  $(basename "$p")"
        git apply "$p" 2>/dev/null || echo "    (already applied or N/A, skipping)"
    done

    # --- Additional source fixes not expressible as simple patches ---

    # OIDN: CUDA 13 dropped sm_70. Sed-patch at build time.
    local OIDN="build_files/build_environment/cmake/openimagedenoise.cmake"
    if ! grep -q "sm_70.*sm_75" "$OIDN" 2>/dev/null; then
        sed -i '/attrib\.type/,/^  )/ {
            /^  )/ a\
  # CUDA 13+: sm_70 (Volta) no longer supported on aarch64\
  if(BLENDER_PLATFORM_ARM)\
    set(ODIN_PATCH_COMMAND ${ODIN_PATCH_COMMAND} \&\&\
      sed -i "s/oidn_set_cuda_sm_flags(OIDN_CUDA_SM_FLAGS 70 75/oidn_set_cuda_sm_flags(OIDN_CUDA_SM_FLAGS 75/g"\
      ${BUILD_DIR}/openimagedenoise/src/external_openimagedenoise/devices/cuda/CMakeLists.txt \&\&\
      sed -i "s/oidn_set_cuda_sm_flags(OIDN_CUDA_SM70_FLAGS 70)/oidn_set_cuda_sm_flags(OIDN_CUDA_SM70_FLAGS 75)/g"\
      ${BUILD_DIR}/openimagedenoise/src/external_openimagedenoise/devices/cuda/CMakeLists.txt \&\&\
      sed -i "s/find_package(CUDAToolkit 12.8/find_package(CUDAToolkit 12.0/g"\
      ${BUILD_DIR}/openimagedenoise/src/external_openimagedenoise/devices/cuda/CMakeLists.txt\
    )\
  endif()
        }' "$OIDN"
    fi

    # libglu: libtool version mismatch, needs autoreconf
    sed -i 's|cd ${BUILD_DIR}/libglu/src/external_libglu/ &&$|cd ${BUILD_DIR}/libglu/src/external_libglu/ \&\& autoreconf -fi \&\&|' \
        build_files/build_environment/cmake/libglu.cmake

    # Wayland/Mesa/Vulkan: meson installs to lib/ not lib64/ on aarch64
    sed -i 's|harvest(external_wayland wayland/lib64 wayland/lib64 "\*")|if(BLENDER_PLATFORM_ARM)\n  harvest(external_wayland wayland/lib wayland/lib64 "*")\nelse()\n  harvest(external_wayland wayland/lib64 wayland/lib64 "*")\nendif()|' \
        build_files/build_environment/cmake/wayland.cmake
    sed -i 's|harvest(external_mesa mesa/lib64 mesa/lib "\*${SHAREDLIBEXT}\*")|if(BLENDER_PLATFORM_ARM)\n  harvest(external_mesa mesa/lib mesa/lib "*${SHAREDLIBEXT}*")\nelse()\n  harvest(external_mesa mesa/lib64 mesa/lib "*${SHAREDLIBEXT}*")\nendif()|' \
        build_files/build_environment/cmake/mesa.cmake
    sed -i 's|-DPKG_WAYLAND_LIBRARY_DIRS=${LIBDIR}/wayland/lib64|-DPKG_WAYLAND_LIBRARY_DIRS=${LIBDIR}/wayland/lib|' \
        build_files/build_environment/cmake/vulkan.cmake
    sed -i 's|wayland/lib64/pkgconfig:|wayland/lib64/pkgconfig:${LIBDIR}/wayland/lib/pkgconfig:|' \
        build_files/build_environment/cmake/wayland_protocols.cmake
    sed -i '/wayland\/lib64\/pkgconfig/ { /wayland\/lib\/pkgconfig/! s|wayland/lib64/pkgconfig:|wayland/lib64/pkgconfig:\\\n${LIBDIR}/wayland/lib/pkgconfig:|; }' \
        build_files/build_environment/cmake/wayland_weston.cmake

    # FFmpeg kmsgrab needs libdrm
    if ! grep -q "DRM_LIBRARY" build_files/cmake/platform/platform_unix.cmake; then
        sed -i '/list(APPEND PLATFORM_LINKLIBS ${CMAKE_DL_LIBS})/a\
endif()\n\n# FFmpeg kmsgrab/hwcontext_drm require libdrm\nif(CMAKE_SYSTEM_NAME STREQUAL "Linux")\n  find_library(DRM_LIBRARY drm)\n  if(DRM_LIBRARY)\n    list(APPEND PLATFORM_LINKLIBS ${DRM_LIBRARY})\n  endif()' \
            build_files/cmake/platform/platform_unix.cmake
    fi

    git add -A
    git commit -m "Apply ARM64 + GB10 patches for v${BLENDER_VERSION}" || true

    echo "=== Patches applied ==="
}

# ---------------------------------------------------------------------------
# Step 4: Build dependencies (~45 min)
# ---------------------------------------------------------------------------
build_deps() {
    echo "=== [4/6] Building dependencies (this takes ~45 minutes) ==="
    echo "    Log: $LOG_FILE"
    cd "$BLENDER_SRC"

    export LANG=en_US.UTF-8
    export CC=gcc
    export CXX=g++

    make deps 2>&1 | tee "$LOG_FILE"

    echo "=== Dependencies built ==="
}

# ---------------------------------------------------------------------------
# Step 5: Build Blender (~10 min)
# ---------------------------------------------------------------------------
build_blender() {
    echo "=== [5/6] Building Blender ${BLENDER_VERSION} ==="
    mkdir -p "$BUILD_DIR"
    cd "$BUILD_DIR"

    cmake \
        -C "$BLENDER_SRC/build_files/cmake/config/blender_release.cmake" \
        -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DWITH_LIBS_PRECOMPILED=ON \
        -DLIBDIR="$LIBDIR" \
        -DWITH_INSTALL_PORTABLE=ON \
        -DCMAKE_C_COMPILER_LAUNCHER=ccache \
        -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
        "$BLENDER_SRC"

    ninja -j$(nproc)
    ninja install

    echo "=== Blender built ==="
}

# ---------------------------------------------------------------------------
# Step 6: Install
# ---------------------------------------------------------------------------
install_blender() {
    echo "=== [6/6] Installing ==="

    sudo ln -sf "$BUILD_DIR/bin/blender" /usr/local/bin/blender

    echo ""
    echo "================================================"
    blender --version | head -1
    echo "================================================"
    echo ""
    echo "Installed: /usr/local/bin/blender"
    echo ""
    echo "Verify GPU:"
    echo '  blender -b --factory-startup --python-expr "import bpy; p=bpy.context.preferences.addons[\"cycles\"].preferences; p.get_devices(); print([d.name for d in p.get_devices_for_type(\"CUDA\")])"'
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
case "$step" in
    deps)       install_deps ;;
    clone)      clone_source ;;
    patch)      apply_patches ;;
    build-deps) build_deps ;;
    build)      build_blender ;;
    install)    install_blender ;;
    all)
        install_deps
        clone_source
        apply_patches
        build_deps
        build_blender
        install_blender
        ;;
    *)
        echo "Usage: $0 [deps|clone|patch|build-deps|build|install|all]"
        exit 1
        ;;
esac
