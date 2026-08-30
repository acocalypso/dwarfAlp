#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR=/opt/re-tools
readonly OUTPUT_ROOT=/output

usage() {
    cat <<'EOF'
Usage:
  run-analysis.sh versions
  run-analysis.sh apk [APKS_FILE] [OUTPUT_NAME]
  run-analysis.sh firmware [FIRMWARE_ZIP] [OUTPUT_NAME]
  run-analysis.sh decompile ELF_FILE [OUTPUT_NAME] [TIMEOUT_SECONDS] [LIBRARY_PATHS]
  run-analysis.sh triage ELF_FILE [OUTPUT_NAME] [TIMEOUT_SECONDS] [LIBRARY_PATHS]
  run-analysis.sh inventory ELF_FILE [OUTPUT_NAME] [TIMEOUT_SECONDS] [LIBRARY_PATHS]
  run-analysis.sh all [APKS_FILE] [FIRMWARE_ZIP]

Inputs below /input are mounted read-only. All generated output is written below
/output, which should be an ignored host directory.
EOF
}

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 2
}

require_file() {
    [[ -f "$1" ]] || fail "input file does not exist: $1"
}

safe_name() {
    local value="$1"
    value="${value##*/}"
    value="${value%.*}"
    printf '%s' "$value" | tr -c 'A-Za-z0-9._-' '_'
}

fresh_output() {
    local path="$1"
    [[ "$path" == "$OUTPUT_ROOT"/* ]] || fail "output escaped $OUTPUT_ROOT: $path"
    if [[ -e "$path" ]]; then
        fail "output already exists; move or remove it explicitly first: $path"
    fi
    mkdir -p "$path"
}

write_hash() {
    local input="$1"
    local output="$2"
    sha256sum "$input" | sed "s#  .*#  $(basename "$input")#" > "$output"
}

extract_zip_safe() {
    local archive="$1"
    local destination="$2"
    python3 - "$archive" "$destination" <<'PY'
from pathlib import Path
from zipfile import ZipFile
import sys

archive = Path(sys.argv[1])
destination = Path(sys.argv[2]).resolve()
with ZipFile(archive) as source:
    for member in source.infolist():
        target = (destination / member.filename).resolve()
        if destination not in target.parents and target != destination:
            raise SystemExit(f"unsafe ZIP member: {member.filename}")
    source.extractall(destination)
PY
}

show_versions() {
    jadx --version
    apktool --version
    analyzeHeadless 2>&1 | sed -n '1,8p' || true
    java -version
    protoc --version
    dtc --version
}

analyze_apk() {
    local bundle="${1:-/input/apk/DWARFLAB_3.4.1_apkcube.apks}"
    local name="${2:-$(safe_name "$bundle")}"
    local output="$OUTPUT_ROOT/apk/$name"
    require_file "$bundle"
    fresh_output "$output"

    write_hash "$bundle" "$output/source.sha256"
    mkdir "$output/apk-set"
    extract_zip_safe "$bundle" "$output/apk-set"
    require_file "$output/apk-set/base.apk"

    # JADX 1.5.4+ understands APKS containers, so it sees base and split DEX/code.
    set +e
    jadx --deobf --show-bad-code --output-dir "$output/jadx" "$bundle" \
        2>&1 | tee "$output/jadx.log"
    local jadx_status="${PIPESTATUS[0]}"
    set -e
    if [[ "$jadx_status" -ne 0 ]]; then
        if [[ -d "$output/jadx/sources" ]]; then
            printf 'warning: JADX returned %s; preserving partial output (see jadx.log)\n' \
                "$jadx_status" | tee "$output/jadx-status.txt" >&2
        else
            fail "JADX failed before producing sources (status $jadx_status)"
        fi
    fi
    apktool decode --force --output "$output/apktool" "$output/apk-set/base.apk" \
        2>&1 | tee "$output/apktool.log"

    mkdir -p "$output/native"
    while IFS= read -r split; do
        unzip -q -o "$split" 'lib/*' -d "$output/native" || true
    done < <(find "$output/apk-set" -maxdepth 1 -type f -name '*.apk' | sort)

    find "$output/apk-set" -maxdepth 1 -type f -name '*.apk' -printf '%f\n' | sort \
        > "$output/apk-files.txt"
    find "$output/native" -type f -print0 | sort -z | xargs -0 -r file \
        > "$output/native-files.txt"
    printf 'APK analysis written to %s\n' "$output"
}

extract_firmware() {
    local bundle="${1:-/input/firmware/dwarf_mini_upgrade_firmware_v1.1.3.2.zip}"
    local name="${2:-$(safe_name "$bundle")}"
    local output="$OUTPUT_ROOT/firmware/$name"
    require_file "$bundle"
    fresh_output "$output"

    write_hash "$bundle" "$output/source.sha256"
    mkdir "$output/extracted"
    extract_zip_safe "$bundle" "$output/extracted"

    find "$output/extracted" -type f -print0 | sort -z | xargs -0 file \
        > "$output/files.txt"
    while IFS= read -r -d '' binary; do
        if file -b "$binary" | grep -q '^ELF '; then
            relative="${binary#"$output/extracted/"}"
            printf '### %s\n' "$relative"
            readelf -h "$binary" | grep -E 'Class:|Data:|OS/ABI:|Type:|Machine:|Entry point'
            readelf -d "$binary" 2>/dev/null | grep -E 'NEEDED|SONAME|RPATH|RUNPATH' || true
        fi
    done < <(find "$output/extracted" -type f -print0 | sort -z) \
        > "$output/elf-inventory.txt"
    printf 'Firmware extraction written to %s\n' "$output"
}

decompile_elf() {
    local binary="${1:-}"
    [[ -n "$binary" ]] || fail 'decompile requires an ELF path'
    local name="${2:-$(safe_name "$binary")}"
    local timeout="${3:-1800}"
    local library_paths="${4:-}"
    require_file "$binary"
    file -b "$binary" | grep -q '^ELF ' || fail "not an ELF file: $binary"
    [[ "$timeout" =~ ^[1-9][0-9]*$ ]] || fail "timeout must be a positive integer"

    local output="$OUTPUT_ROOT/ghidra/$name"
    fresh_output "$output"
    mkdir "$output/project" "$output/decompiled"
    write_hash "$binary" "$output/source.sha256"
    file -b "$binary" > "$output/source.file"

    local -a library_args=()
    if [[ -n "$library_paths" ]]; then
        library_args=(
            -librarySearchPaths "$library_paths"
            -loader ElfLoader
            -loader-loadLibraries true
            -loader-libraryLoadDepth 2
            -loader-linkExistingProjectLibraries true
        )
    fi

    analyzeHeadless "$output/project" project \
        -import "$binary" \
        "${library_args[@]}" \
        -overwrite \
        -analysisTimeoutPerFile "$timeout" \
        -scriptPath "$SCRIPT_DIR/ghidra_scripts" \
        -postScript ExportDecompilation.java "$output/decompiled" \
        -deleteProject \
        2>&1 | tee "$output/ghidra.log"
    printf 'Ghidra decompilation written to %s\n' "$output"
}

triage_elf() {
    local binary="${1:-}"
    [[ -n "$binary" ]] || fail 'triage requires an ELF path'
    local name="${2:-$(safe_name "$binary")-triage}"
    local timeout="${3:-1800}"
    local library_paths="${4:-}"
    require_file "$binary"
    file -b "$binary" | grep -q '^ELF ' || fail "not an ELF file: $binary"
    [[ "$timeout" =~ ^[1-9][0-9]*$ ]] || fail "timeout must be a positive integer"

    local output="$OUTPUT_ROOT/ghidra/$name"
    fresh_output "$output"
    mkdir "$output/project" "$output/decompiled"
    write_hash "$binary" "$output/source.sha256"
    file -b "$binary" > "$output/source.file"

    local -a library_args=()
    if [[ -n "$library_paths" ]]; then
        library_args=(
            -librarySearchPaths "$library_paths"
            -loader ElfLoader
            -loader-loadLibraries true
            -loader-libraryLoadDepth 2
            -loader-linkExistingProjectLibraries true
        )
    fi

    analyzeHeadless "$output/project" project \
        -import "$binary" \
        "${library_args[@]}" \
        -overwrite \
        -analysisTimeoutPerFile "$timeout" \
        -scriptPath "$SCRIPT_DIR/ghidra_scripts" \
        -postScript ExportKeywordXrefs.java "$output/decompiled" \
        -deleteProject \
        2>&1 | tee "$output/ghidra.log"
    printf 'Ghidra keyword triage written to %s\n' "$output"
}

inventory_elf() {
    local binary="${1:-}"
    [[ -n "$binary" ]] || fail 'inventory requires an ELF path'
    local name="${2:-$(safe_name "$binary")-inventory}"
    local timeout="${3:-1800}"
    local library_paths="${4:-}"
    require_file "$binary"
    file -b "$binary" | grep -q '^ELF ' || fail "not an ELF file: $binary"
    [[ "$timeout" =~ ^[1-9][0-9]*$ ]] || fail "timeout must be a positive integer"

    local output="$OUTPUT_ROOT/ghidra/$name"
    fresh_output "$output"
    mkdir "$output/project" "$output/inventory"
    write_hash "$binary" "$output/source.sha256"
    file -b "$binary" > "$output/source.file"

    local -a library_args=()
    if [[ -n "$library_paths" ]]; then
        library_args=(
            -librarySearchPaths "$library_paths"
            -loader ElfLoader
            -loader-loadLibraries true
            -loader-libraryLoadDepth 2
            -loader-linkExistingProjectLibraries true
        )
    fi

    analyzeHeadless "$output/project" project \
        -import "$binary" \
        "${library_args[@]}" \
        -overwrite \
        -analysisTimeoutPerFile "$timeout" \
        -scriptPath "$SCRIPT_DIR/ghidra_scripts" \
        -postScript ExportProgramInventory.java "$output/inventory" \
        -deleteProject \
        2>&1 | tee "$output/ghidra.log"
    printf 'Ghidra program inventory written to %s\n' "$output"
}

case "${1:-help}" in
    versions)
        show_versions
        ;;
    apk)
        analyze_apk "${2:-}" "${3:-}"
        ;;
    firmware)
        extract_firmware "${2:-}" "${3:-}"
        ;;
    decompile)
        decompile_elf "${2:-}" "${3:-}" "${4:-1800}" "${5:-}"
        ;;
    triage)
        triage_elf "${2:-}" "${3:-}" "${4:-1800}" "${5:-}"
        ;;
    inventory)
        inventory_elf "${2:-}" "${3:-}" "${4:-1800}" "${5:-}"
        ;;
    all)
        analyze_apk "${2:-}" ""
        extract_firmware "${3:-}" ""
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        usage >&2
        fail "unknown command: $1"
        ;;
esac
