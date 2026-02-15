#!/usr/bin/env bash
# ===========================================================================
# Blender 5.0.1 Build Script for NVIDIA DGX Spark / GB10
# Ubuntu 24.04 LTS (aarch64) + CUDA 13
# ===========================================================================
# Usage: ./setup.sh [options] [step]
#   Steps: deps, clone, patch, build-deps, build, install, all
#   Default: all (runs everything)
#
# Options:
#   --help      Show this help message
#   --status    Show checkpoint status for all steps
#   --clean     Remove all checkpoints and build directory
#   --force     Ignore checkpoints, re-run the specified step
#   --verbose   Show full command output (default: summarized)
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
LOG_DIR="$PROJECT_DIR/logs"
CHECKPOINT_DIR="$PROJECT_DIR/.checkpoints"

FORCE=false
VERBOSE=false
STEP_START_TIME=0
SCRIPT_START_TIME=0
CURRENT_STEP=""
SPINNER_PID=""

# Ordered list of steps (used for downstream invalidation)
STEPS=(deps clone patch build-deps build install)

# ═══════════════════════════════════════════════════════════════════════════
# Color / Output Functions
# ═══════════════════════════════════════════════════════════════════════════

# Auto-detect TTY; disable colors when piped or NO_COLOR is set
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    MAGENTA='\033[0;35m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' MAGENTA='' CYAN='' BOLD='' DIM='' RESET=''
fi

info()    { echo -e "  ${BLUE}ℹ${RESET} $*"; }
success() { echo -e "  ${GREEN}✓${RESET} $*"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET} $*"; }
error()   { echo -e "  ${RED}✗${RESET} $*" >&2; }
detail()  { echo -e "    ${DIM}$*${RESET}"; }

header() {
    local step_num="$1"
    local total="$2"
    local title="$3"
    local line
    line=$(printf '═%.0s' {1..54})
    echo ""
    echo -e "${BOLD}${CYAN}${line}${RESET}"
    echo -e "${BOLD}${CYAN}  [${step_num}/${total}] ${title}${RESET}"
    echo -e "${BOLD}${CYAN}${line}${RESET}"
    echo ""
}

print_banner() {
    echo ""
    echo -e "${BOLD}${MAGENTA}  ╔══════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${MAGENTA}  ║   Blender ${BLENDER_VERSION} — GB10 / DGX Spark Builder       ║${RESET}"
    echo -e "${BOLD}${MAGENTA}  ║   Ubuntu 24.04 aarch64 + CUDA 13               ║${RESET}"
    echo -e "${BOLD}${MAGENTA}  ╚══════════════════════════════════════════════════╝${RESET}"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════
# Timing Helpers
# ═══════════════════════════════════════════════════════════════════════════

now_seconds() { date +%s; }

format_duration() {
    local seconds="$1"
    if (( seconds < 60 )); then
        echo "${seconds}s"
    elif (( seconds < 3600 )); then
        printf '%dm %02ds' $((seconds / 60)) $((seconds % 60))
    else
        printf '%dh %02dm %02ds' $((seconds / 3600)) $(((seconds % 3600) / 60)) $((seconds % 60))
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
# Spinner for Long-Running Steps
# ═══════════════════════════════════════════════════════════════════════════

start_spinner() {
    local msg="$1"
    local log_file="${2:-}"
    if [[ ! -t 1 ]]; then
        info "$msg"
        return
    fi
    (
        local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
        local i=0
        local tail_line=""
        while true; do
            if [[ -n "$log_file" ]] && [[ -f "$log_file" ]]; then
                tail_line=$(tail -1 "$log_file" 2>/dev/null | head -c 60 || true)
            fi
            printf "\r  ${CYAN}%s${RESET} %s ${DIM}%s${RESET}%s" \
                "${frames[$i]}" "$msg" "$tail_line" "$(printf ' %.0s' {1..20})"
            i=$(( (i + 1) % ${#frames[@]} ))
            sleep 0.15
        done
    ) &
    SPINNER_PID=$!
    disown "$SPINNER_PID" 2>/dev/null
}

stop_spinner() {
    if [[ -n "${SPINNER_PID:-}" ]]; then
        kill "$SPINNER_PID" 2>/dev/null || true
        wait "$SPINNER_PID" 2>/dev/null || true
        SPINNER_PID=""
        printf "\r%s\r" "$(printf ' %.0s' {1..100})"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
# Checkpoint / Resume System
# ═══════════════════════════════════════════════════════════════════════════

mark_done() {
    local step="$1"
    mkdir -p "$CHECKPOINT_DIR"
    date -Iseconds > "$CHECKPOINT_DIR/${step}.done"
}

is_done() {
    local step="$1"
    [[ -f "$CHECKPOINT_DIR/${step}.done" ]]
}

invalidate_downstream() {
    local target="$1"
    local found=false
    for s in "${STEPS[@]}"; do
        if [[ "$found" == true ]]; then
            if [[ -f "$CHECKPOINT_DIR/${s}.done" ]]; then
                rm -f "$CHECKPOINT_DIR/${s}.done"
                warn "Invalidated downstream checkpoint: ${BOLD}$s${RESET}"
            fi
        fi
        if [[ "$s" == "$target" ]]; then
            found=true
        fi
    done
}

show_status() {
    print_banner
    echo -e "  ${BOLD}Checkpoint Status${RESET}  ${DIM}($CHECKPOINT_DIR)${RESET}"
    echo ""
    local i=1
    for s in "${STEPS[@]}"; do
        if is_done "$s"; then
            local ts
            ts=$(cat "$CHECKPOINT_DIR/${s}.done")
            echo -e "    ${GREEN}✓${RESET} [${i}/6] ${BOLD}$s${RESET}  ${DIM}— completed $ts${RESET}"
        else
            echo -e "    ${DIM}○${RESET} [${i}/6] ${BOLD}$s${RESET}  ${DIM}— pending${RESET}"
        fi
        ((i++))
    done
    echo ""
}

clean_all() {
    print_banner
    warn "Cleaning all checkpoints and build artifacts..."
    if [[ -d "$CHECKPOINT_DIR" ]]; then
        rm -rf "$CHECKPOINT_DIR"
        success "Removed $CHECKPOINT_DIR"
    fi
    if [[ -d "$BUILD_DIR" ]]; then
        rm -rf "$BUILD_DIR"
        success "Removed $BUILD_DIR"
    fi
    if [[ -d "$LOG_DIR" ]]; then
        rm -rf "$LOG_DIR"
        success "Removed $LOG_DIR"
    fi
    success "Clean complete"
}

# ═══════════════════════════════════════════════════════════════════════════
# Error Handling
# ═══════════════════════════════════════════════════════════════════════════

on_error() {
    local exit_code=$?
    stop_spinner
    echo ""
    echo -e "  ${RED}${BOLD}━━━ BUILD FAILED ━━━${RESET}"
    echo ""
    if [[ -n "$CURRENT_STEP" ]]; then
        error "Step failed: ${BOLD}$CURRENT_STEP${RESET} (exit code $exit_code)"
        local log_file="$LOG_DIR/${CURRENT_STEP}.log"
        if [[ -f "$log_file" ]]; then
            error "Log file: ${BOLD}$log_file${RESET}"
            echo ""
            echo -e "  ${DIM}Last 15 lines of log:${RESET}"
            tail -15 "$log_file" 2>/dev/null | while IFS= read -r line; do
                echo -e "    ${DIM}$line${RESET}"
            done
        fi
        echo ""
        case "$CURRENT_STEP" in
            deps)
                info "Try: Check your internet connection and apt sources"
                info "     sudo apt-get update && ./setup.sh deps"
                ;;
            clone)
                info "Try: Check network connectivity to github.com"
                info "     rm -rf $BLENDER_SRC && ./setup.sh clone"
                ;;
            patch)
                info "Try: Ensure source is clean: cd $BLENDER_SRC && git checkout ."
                info "     Then re-run: ./setup.sh --force patch"
                ;;
            build-deps)
                info "Try: Check the log above for the specific library that failed"
                info "     Re-run: ./setup.sh --force build-deps"
                ;;
            build)
                info "Try: Check cmake/ninja errors in the log"
                info "     Re-run: ./setup.sh --force build"
                ;;
            install)
                info "Try: Ensure the build completed: ls $BUILD_DIR/bin/blender"
                info "     Re-run: ./setup.sh install"
                ;;
        esac
    else
        error "Build failed (exit code $exit_code)"
    fi
    echo ""
    exit "$exit_code"
}

trap on_error ERR

# ═══════════════════════════════════════════════════════════════════════════
# Pre-flight Checks
# ═══════════════════════════════════════════════════════════════════════════

preflight_checks() {
    header "0" "6" "Pre-flight checks"

    # Architecture
    local arch
    arch=$(uname -m)
    if [[ "$arch" != "aarch64" ]]; then
        error "This script requires aarch64. Detected: $arch"
        exit 1
    fi
    success "Architecture: $arch"

    # Disk space
    local free_gb
    free_gb=$(df --output=avail "$HOME" | tail -1 | awk '{printf "%.0f", $1/1048576}')
    if (( free_gb < 50 )); then
        error "Insufficient disk space: ${free_gb}GB free (need 50GB+)"
        exit 1
    elif (( free_gb < 60 )); then
        warn "Low disk space: ${free_gb}GB free (recommend 60GB+)"
    else
        success "Disk space: ${free_gb}GB free"
    fi

    # Required tools
    local tools=(git cmake ninja gcc g++ python3 make sudo)
    local missing=()
    for tool in "${tools[@]}"; do
        if ! command -v "$tool" &>/dev/null; then
            missing+=("$tool")
        fi
    done
    if (( ${#missing[@]} > 0 )); then
        error "Missing required tools: ${missing[*]}"
        info "Install with: sudo apt-get install ${missing[*]}"
        exit 1
    fi
    success "Required tools: all present"

    # CUDA
    if [[ -x /usr/local/cuda/bin/nvcc ]]; then
        local cuda_ver
        cuda_ver=$(/usr/local/cuda/bin/nvcc --version 2>/dev/null | grep -oP 'release \K[\d.]+' || echo "unknown")
        success "CUDA: $cuda_ver (/usr/local/cuda/bin/nvcc)"
    else
        warn "CUDA nvcc not found at /usr/local/cuda/bin/nvcc"
        info "GPU-accelerated features (Cycles CUDA) may not build"
    fi

    # Network (quick check)
    if curl -sf --max-time 5 https://github.com &>/dev/null; then
        success "Network: github.com reachable"
    else
        warn "Cannot reach github.com — clone step may fail"
    fi

    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════
# Step Validation Functions
# ═══════════════════════════════════════════════════════════════════════════

validate_deps() {
    local pkgs=(build-essential cmake ninja-build git-lfs)
    local failed=false
    for pkg in "${pkgs[@]}"; do
        if ! dpkg -s "$pkg" &>/dev/null; then
            error "Package not installed: $pkg"
            failed=true
        fi
    done
    if [[ "$failed" == true ]]; then
        return 1
    fi
    success "Validation: key packages confirmed installed"
}

validate_clone() {
    if [[ ! -f "$BLENDER_SRC/CMakeLists.txt" ]]; then
        error "Validation failed: $BLENDER_SRC/CMakeLists.txt not found"
        return 1
    fi
    # Check LFS files are real (>1KB, not pointer stubs)
    local lfs_file
    lfs_file=$(find "$BLENDER_SRC/release/datafiles" -type f -name "*.blend" 2>/dev/null | head -1 || true)
    if [[ -n "$lfs_file" ]]; then
        local size
        size=$(stat -c%s "$lfs_file" 2>/dev/null || echo 0)
        if (( size < 1024 )); then
            error "LFS files appear to be stubs (size: ${size}B). Run: cd $BLENDER_SRC && git lfs pull"
            return 1
        fi
        success "Validation: source present, LFS files real (${size}B)"
    else
        success "Validation: source present, CMakeLists.txt found"
    fi
}

validate_patch() {
    # Verify the commit message exists (patches were committed)
    cd "$BLENDER_SRC"
    if ! git log --oneline -1 | grep -q "GB10\|ARM64\|arm64"; then
        error "Validation failed: patch commit not found in git log"
        return 1
    fi
    success "Validation: patch commit present in git history"
}

validate_build_deps() {
    if [[ ! -d "$LIBDIR" ]]; then
        error "Validation failed: $LIBDIR does not exist"
        return 1
    fi
    local count
    count=$(find "$LIBDIR" -type f 2>/dev/null | head -50 | wc -l)
    if (( count < 10 )); then
        error "Validation failed: $LIBDIR has too few files ($count)"
        return 1
    fi
    success "Validation: $LIBDIR exists with $count+ files"
}

validate_build() {
    if [[ ! -x "$BUILD_DIR/bin/blender" ]]; then
        error "Validation failed: $BUILD_DIR/bin/blender not found or not executable"
        return 1
    fi
    success "Validation: blender binary built"
}

validate_install() {
    if ! blender --version &>/dev/null; then
        error "Validation failed: 'blender --version' did not run successfully"
        return 1
    fi
    local ver
    ver=$(blender --version 2>/dev/null | head -1)
    success "Validation: $ver"
}

# ═══════════════════════════════════════════════════════════════════════════
# run_step() — Wrapper with timing, checkpoints, validation
# ═══════════════════════════════════════════════════════════════════════════

# Associative arrays for step metadata
declare -A STEP_NUM=([deps]=1 [clone]=2 [patch]=3 [build-deps]=4 [build]=5 [install]=6)
declare -A STEP_TITLE=(
    [deps]="Installing system dependencies"
    [clone]="Cloning Blender source"
    [patch]="Applying patches"
    [build-deps]="Building dependencies (~45 min)"
    [build]="Building Blender (~10 min)"
    [install]="Installing Blender"
)
declare -A STEP_FUNC=(
    [deps]=install_deps
    [clone]=clone_source
    [patch]=apply_patches
    [build-deps]=build_deps
    [build]=build_blender
    [install]=install_blender
)
declare -A STEP_VALIDATE=(
    [deps]=validate_deps
    [clone]=validate_clone
    [patch]=validate_patch
    [build-deps]=validate_build_deps
    [build]=validate_build
    [install]=validate_install
)
declare -A STEP_TIMINGS

run_step() {
    local step="$1"
    local num="${STEP_NUM[$step]}"
    local title="${STEP_TITLE[$step]}"
    local func="${STEP_FUNC[$step]}"
    local validate="${STEP_VALIDATE[$step]}"

    # Check checkpoint
    if [[ "$FORCE" == false ]] && is_done "$step"; then
        header "$num" "6" "$title"
        local ts
        ts=$(cat "$CHECKPOINT_DIR/${step}.done")
        success "Previously completed ${DIM}($ts)${RESET} — skipping"
        echo ""
        STEP_TIMINGS[$step]="skipped"
        return 0
    fi

    # If forcing, invalidate downstream
    if [[ "$FORCE" == true ]] && is_done "$step"; then
        rm -f "$CHECKPOINT_DIR/${step}.done"
        invalidate_downstream "$step"
    fi

    header "$num" "6" "$title"
    CURRENT_STEP="$step"
    STEP_START_TIME=$(now_seconds)

    mkdir -p "$LOG_DIR"
    local log_file="$LOG_DIR/${step}.log"

    # Run the step function
    "$func"

    # Run validation
    if [[ -n "$validate" ]]; then
        "$validate"
    fi

    local elapsed=$(( $(now_seconds) - STEP_START_TIME ))
    local duration
    duration=$(format_duration "$elapsed")
    STEP_TIMINGS[$step]="$duration"

    mark_done "$step"
    echo ""
    success "${BOLD}${title}${RESET} completed ${DIM}(${duration})${RESET}"
    CURRENT_STEP=""
}

# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Install system dependencies
# ═══════════════════════════════════════════════════════════════════════════

install_deps() {
    info "Updating apt package list..."
    sudo apt-get update -qq

    info "Installing packages..."
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
    info "Checking multiarch symlinks..."
    for dir in bits gnu asm; do
        if [ ! -e "/usr/include/$dir" ] && [ -d "/usr/include/aarch64-linux-gnu/$dir" ]; then
            detail "Symlinking /usr/include/$dir"
            sudo ln -sf "/usr/include/aarch64-linux-gnu/$dir" "/usr/include/$dir"
        fi
    done

    # CUDA 13 removed texture_fetch_functions.h but Clang still references it
    if [ -d /usr/local/cuda ] && [ ! -f /usr/local/cuda/include/texture_fetch_functions.h ]; then
        info "Creating stub texture_fetch_functions.h for CUDA 13"
        sudo touch /usr/local/cuda/include/texture_fetch_functions.h
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Clone Blender source
# ═══════════════════════════════════════════════════════════════════════════

clone_source() {
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"

    if [ -d "$BLENDER_SRC" ]; then
        warn "Source directory already exists: $BLENDER_SRC"
        info "Verifying checkout..."
        if [[ -f "$BLENDER_SRC/CMakeLists.txt" ]]; then
            success "Existing source looks valid, reusing it"
            return
        else
            error "Source directory exists but looks incomplete"
            error "Remove it and re-run: rm -rf $BLENDER_SRC && ./setup.sh clone"
            return 1
        fi
    fi

    info "Cloning Blender v${BLENDER_VERSION} (shallow, LFS deferred)..."
    GIT_LFS_SKIP_SMUDGE=1 git clone \
        -b "v${BLENDER_VERSION}" --depth 1 \
        https://github.com/blender/blender.git

    info "Configuring LFS endpoint (projects.blender.org)..."
    cd "$BLENDER_SRC"
    git config lfs.url https://projects.blender.org/blender/blender.git/info/lfs

    info "Pulling LFS data for release/datafiles..."
    git lfs pull --include="release/datafiles/*"

    cd "$PROJECT_DIR"
}

# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Apply patches
# ═══════════════════════════════════════════════════════════════════════════

apply_patches() {
    cd "$BLENDER_SRC"

    git config user.email "builder@local"
    git config user.name "Builder"

    # Check if patches are already committed
    if git log --oneline | grep -q "GB10 patches\|ARM64.*GB10"; then
        success "Patches already committed — skipping"
        return
    fi

    # Apply .patch files with proper already-applied detection
    local patch_count=0
    local applied_count=0
    local skipped_count=0
    for p in "$PATCH_DIR"/*.patch; do
        [[ -f "$p" ]] || continue
        ((patch_count++))
        local name
        name=$(basename "$p")

        # Check if already applied (reverse-apply test)
        if git apply --check --reverse "$p" &>/dev/null; then
            detail "$name ${DIM}(already applied)${RESET}"
            ((skipped_count++))
            continue
        fi

        # Attempt to apply
        if git apply --check "$p" &>/dev/null; then
            git apply "$p"
            success "$name"
            ((applied_count++))
        else
            error "Patch failed to apply cleanly: $name"
            error "Check if the source tree is in the expected state"
            return 1
        fi
    done
    info "Patches: $applied_count applied, $skipped_count already applied (of $patch_count total)"

    # --- Additional source fixes not expressible as simple patches ---

    info "Applying inline source fixes..."

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
        detail "OIDN: sm_70 removal for CUDA 13"
    else
        detail "OIDN: already patched"
    fi

    # libglu: libtool version mismatch, needs autoreconf
    if ! grep -q 'autoreconf -fi' build_files/build_environment/cmake/libglu.cmake 2>/dev/null; then
        sed -i 's|cd ${BUILD_DIR}/libglu/src/external_libglu/ &&$|cd ${BUILD_DIR}/libglu/src/external_libglu/ \&\& autoreconf -fi \&\&|' \
            build_files/build_environment/cmake/libglu.cmake
        detail "libglu: added autoreconf"
    else
        detail "libglu: already patched"
    fi

    # Wayland: meson installs to lib/ not lib64/ on aarch64
    if ! grep -q 'BLENDER_PLATFORM_ARM' build_files/build_environment/cmake/wayland.cmake 2>/dev/null; then
        sed -i 's|harvest(external_wayland wayland/lib64 wayland/lib64 "\*")|if(BLENDER_PLATFORM_ARM)\n  harvest(external_wayland wayland/lib wayland/lib64 "*")\nelse()\n  harvest(external_wayland wayland/lib64 wayland/lib64 "*")\nendif()|' \
            build_files/build_environment/cmake/wayland.cmake
        detail "Wayland: lib path fix"
    else
        detail "Wayland: already patched"
    fi

    # Mesa: lib/ vs lib64/
    if ! grep -q 'BLENDER_PLATFORM_ARM' build_files/build_environment/cmake/mesa.cmake 2>/dev/null; then
        sed -i 's|harvest(external_mesa mesa/lib64 mesa/lib "\*${SHAREDLIBEXT}\*")|if(BLENDER_PLATFORM_ARM)\n  harvest(external_mesa mesa/lib mesa/lib "*${SHAREDLIBEXT}*")\nelse()\n  harvest(external_mesa mesa/lib64 mesa/lib "*${SHAREDLIBEXT}*")\nendif()|' \
            build_files/build_environment/cmake/mesa.cmake
        detail "Mesa: lib path fix"
    else
        detail "Mesa: already patched"
    fi

    # Vulkan: wayland lib path
    if grep -q 'wayland/lib64' build_files/build_environment/cmake/vulkan.cmake 2>/dev/null && \
       ! grep -q 'wayland/lib\b' build_files/build_environment/cmake/vulkan.cmake 2>/dev/null; then
        sed -i 's|-DPKG_WAYLAND_LIBRARY_DIRS=${LIBDIR}/wayland/lib64|-DPKG_WAYLAND_LIBRARY_DIRS=${LIBDIR}/wayland/lib|' \
            build_files/build_environment/cmake/vulkan.cmake
        detail "Vulkan: wayland lib path fix"
    else
        detail "Vulkan: already patched"
    fi

    # Wayland protocols: pkgconfig path
    if ! grep -q 'wayland/lib/pkgconfig' build_files/build_environment/cmake/wayland_protocols.cmake 2>/dev/null; then
        sed -i 's|wayland/lib64/pkgconfig:|wayland/lib64/pkgconfig:${LIBDIR}/wayland/lib/pkgconfig:|' \
            build_files/build_environment/cmake/wayland_protocols.cmake
        detail "Wayland protocols: pkgconfig path fix"
    else
        detail "Wayland protocols: already patched"
    fi

    # Wayland weston: pkgconfig path
    if ! grep -q 'wayland/lib/pkgconfig' build_files/build_environment/cmake/wayland_weston.cmake 2>/dev/null; then
        sed -i '/wayland\/lib64\/pkgconfig/ { /wayland\/lib\/pkgconfig/! s|wayland/lib64/pkgconfig:|wayland/lib64/pkgconfig:\\\n${LIBDIR}/wayland/lib/pkgconfig:|; }' \
            build_files/build_environment/cmake/wayland_weston.cmake
        detail "Wayland weston: pkgconfig path fix"
    else
        detail "Wayland weston: already patched"
    fi

    # FFmpeg kmsgrab needs libdrm
    if ! grep -q "DRM_LIBRARY" build_files/cmake/platform/platform_unix.cmake 2>/dev/null; then
        sed -i '/list(APPEND PLATFORM_LINKLIBS ${CMAKE_DL_LIBS})/a\
endif()\n\n# FFmpeg kmsgrab/hwcontext_drm require libdrm\nif(CMAKE_SYSTEM_NAME STREQUAL "Linux")\n  find_library(DRM_LIBRARY drm)\n  if(DRM_LIBRARY)\n    list(APPEND PLATFORM_LINKLIBS ${DRM_LIBRARY})\n  endif()' \
            build_files/cmake/platform/platform_unix.cmake
        detail "FFmpeg: libdrm link fix"
    else
        detail "FFmpeg: already patched"
    fi

    info "Committing patches..."
    git add -A
    git commit -m "Apply ARM64 + GB10 patches for v${BLENDER_VERSION}" || true
}

# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Build dependencies (~45 min)
# ═══════════════════════════════════════════════════════════════════════════

build_deps() {
    cd "$BLENDER_SRC"

    export LANG=en_US.UTF-8
    export CC=gcc
    export CXX=g++

    local log_file="$LOG_DIR/build-deps.log"
    mkdir -p "$LOG_DIR"

    info "Building precompiled libraries (this takes ~45 minutes)..."
    detail "Log: $log_file"

    if [[ "$VERBOSE" == true ]]; then
        make deps 2>&1 | tee "$log_file"
    else
        start_spinner "Building libraries..." "$log_file"
        make deps > "$log_file" 2>&1
        stop_spinner
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Build Blender (~10 min)
# ═══════════════════════════════════════════════════════════════════════════

build_blender() {
    mkdir -p "$BUILD_DIR"
    cd "$BUILD_DIR"

    local log_file="$LOG_DIR/build.log"
    mkdir -p "$LOG_DIR"

    info "Configuring CMake..."
    cmake \
        -C "$BLENDER_SRC/build_files/cmake/config/blender_release.cmake" \
        -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DWITH_LIBS_PRECOMPILED=ON \
        -DLIBDIR="$LIBDIR" \
        -DWITH_INSTALL_PORTABLE=ON \
        -DCMAKE_C_COMPILER_LAUNCHER=ccache \
        -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
        "$BLENDER_SRC" 2>&1 | tee "$LOG_DIR/cmake-config.log"

    info "Building with Ninja ($(nproc) cores)..."
    detail "Log: $log_file"

    if [[ "$VERBOSE" == true ]]; then
        ninja -j"$(nproc)" 2>&1 | tee "$log_file"
    else
        start_spinner "Compiling Blender..." "$log_file"
        ninja -j"$(nproc)" > "$log_file" 2>&1
        stop_spinner
    fi

    info "Running ninja install..."
    ninja install
}

# ═══════════════════════════════════════════════════════════════════════════
# Step 6: Install
# ═══════════════════════════════════════════════════════════════════════════

install_blender() {
    info "Creating symlink: /usr/local/bin/blender"
    sudo ln -sf "$BUILD_DIR/bin/blender" /usr/local/bin/blender

    local ver
    ver=$(blender --version 2>/dev/null | head -1 || echo "unknown")
    success "Installed: $ver"
    detail "Binary: /usr/local/bin/blender -> $BUILD_DIR/bin/blender"

    echo ""
    info "Verify GPU with:"
    detail 'blender -b --factory-startup --python-expr "import bpy; p=bpy.context.preferences.addons[\"cycles\"].preferences; p.get_devices(); print([d.name for d in p.get_devices_for_type(\"CUDA\")])"'
}

# ═══════════════════════════════════════════════════════════════════════════
# Final Summary
# ═══════════════════════════════════════════════════════════════════════════

print_summary() {
    local total_elapsed=$(( $(now_seconds) - SCRIPT_START_TIME ))
    local total_duration
    total_duration=$(format_duration "$total_elapsed")

    echo ""
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════${RESET}"
    echo -e "${BOLD}${CYAN}  Build Summary${RESET}"
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════${RESET}"
    echo ""

    for s in "${STEPS[@]}"; do
        local timing="${STEP_TIMINGS[$s]:-n/a}"
        local title="${STEP_TITLE[$s]}"
        if is_done "$s"; then
            if [[ "$timing" == "skipped" ]]; then
                echo -e "    ${DIM}⊘${RESET} ${title}  ${DIM}(skipped — cached)${RESET}"
            else
                echo -e "    ${GREEN}✓${RESET} ${title}  ${DIM}(${timing})${RESET}"
            fi
        else
            echo -e "    ${DIM}○${RESET} ${title}  ${DIM}(not run)${RESET}"
        fi
    done

    echo ""
    echo -e "  ${BOLD}Total time: ${total_duration}${RESET}"

    # Show Blender version if installed
    if command -v blender &>/dev/null; then
        local ver
        ver=$(blender --version 2>/dev/null | head -1 || echo "")
        if [[ -n "$ver" ]]; then
            echo -e "  ${BOLD}$ver${RESET}"
        fi
    fi

    # GPU detection
    if [[ -x /usr/local/cuda/bin/nvcc ]]; then
        local gpu
        gpu=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "")
        if [[ -n "$gpu" ]]; then
            echo -e "  ${BOLD}GPU: $gpu${RESET}"
        fi
    fi

    echo ""
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════${RESET}"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════
# CLI Help
# ═══════════════════════════════════════════════════════════════════════════

show_help() {
    print_banner
    cat <<'HELP'
  USAGE
    ./setup.sh [options] [step]

  STEPS
    deps          Install system packages and dependencies
    clone         Clone Blender source and pull LFS data
    patch         Apply ARM64/GB10 patches to Blender source
    build-deps    Build precompiled libraries (~45 min)
    build         Build Blender with CMake + Ninja (~10 min)
    install       Symlink blender binary to /usr/local/bin
    all           Run all steps in order (default)

  OPTIONS
    --help        Show this help message
    --status      Show checkpoint status for all steps
    --clean       Remove all checkpoints, logs, and build directory
    --force       Ignore checkpoints and re-run the specified step
    --verbose     Show full command output (default: summarized)

  ENVIRONMENT
    BLENDER_BUILD_DIR   Override build directory (default: ~/blender-gb10-build)
    NO_COLOR            Disable colored output

  EXAMPLES
    ./setup.sh                  # Run all steps
    ./setup.sh deps             # Run only the deps step
    ./setup.sh --force patch    # Re-run patch step (ignoring checkpoint)
    ./setup.sh --status         # Show which steps are complete
    ./setup.sh --clean          # Reset everything and start fresh

HELP
}

# ═══════════════════════════════════════════════════════════════════════════
# Main — Argument Parsing & Dispatch
# ═══════════════════════════════════════════════════════════════════════════

main() {
    local step=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                show_help
                exit 0
                ;;
            --status)
                show_status
                exit 0
                ;;
            --clean)
                clean_all
                exit 0
                ;;
            --force)
                FORCE=true
                shift
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            -*)
                error "Unknown option: $1"
                info "Run './setup.sh --help' for usage"
                exit 1
                ;;
            *)
                if [[ -n "$step" ]]; then
                    error "Multiple steps specified: '$step' and '$1'"
                    info "Run './setup.sh --help' for usage"
                    exit 1
                fi
                step="$1"
                shift
                ;;
        esac
    done

    step="${step:-all}"

    # Validate step name
    case "$step" in
        deps|clone|patch|build-deps|build|install|all) ;;
        *)
            error "Unknown step: $step"
            info "Valid steps: deps, clone, patch, build-deps, build, install, all"
            exit 1
            ;;
    esac

    print_banner
    SCRIPT_START_TIME=$(now_seconds)

    # Pre-flight checks (only when running actual steps)
    preflight_checks

    if [[ "$step" == "all" ]]; then
        for s in "${STEPS[@]}"; do
            run_step "$s"
        done
        print_summary
    else
        run_step "$step"
    fi
}

main "$@"
