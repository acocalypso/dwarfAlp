#!/usr/bin/env bash
set -euo pipefail

root="${1:?usage: scan_elfs.sh EXTRACTED_ROOT}"

while IFS= read -r -d '' binary; do
    if ! file -b "$binary" | grep -q '^ELF '; then
        continue
    fi
    printf '### %s\n' "${binary#"$root"/}"
    readelf -h "$binary" | grep -E 'Class:|Data:|OS/ABI:|Type:|Machine:|Entry point'
    printf '%s\n' 'NEEDED/RPATH'
    readelf -d "$binary" 2>/dev/null | grep -E 'NEEDED|SONAME|RPATH|RUNPATH' || true
    printf '%s\n' 'NOTES'
    readelf -n "$binary" 2>/dev/null | grep -E 'Build ID|ABI:' || true
    printf '%s\n' 'ARM ATTRIBUTES'
    readelf -A "$binary" 2>/dev/null \
        | grep -E 'Tag_CPU_name|Tag_CPU_arch|Tag_ABI_VFP_args|Tag_FP_arch|Tag_Advanced_SIMD_arch' \
        || true
done < <(find "$root" -type f -print0 | sort -z)
