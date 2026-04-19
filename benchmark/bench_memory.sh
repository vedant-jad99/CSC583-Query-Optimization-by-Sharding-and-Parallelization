#!/bin/bash
##############################################################
#
# bench_memory.sh
# ───────────────
# Measures peak resident set size (RSS) of the C++ engine
# during initialization using /usr/bin/time -v (Linux) or
# \time -l (macOS).
#
# Usage:
#   bash benchmark/scripts/bench_memory.sh <engine> <index> <output_file> <phase>
#
# Output:
#   Appends a JSON line to <output_file>:
#   {"phase": N, "timestamp": "...", "peak_rss_kb": N}
#
# Notes:
#   - Measures init-only mode (--bench-init flag)
#   - Run once per benchmark session (memory is deterministic
#     for a fixed index — no need to repeat)
#   - On macOS, RSS is reported in bytes; converted to KB here
#   - Requires /usr/bin/time (not the shell builtin 'time')
#
# Author: Vedant Keshav Jadhav
# Phase:  1, 2, 3 (portable)
#
##############################################################

set -euo pipefail

ENGINE="${1:?Usage: $0 <engine> <index> <output_file> <phase>}"
INDEX="${2:?Usage: $0 <engine> <index> <output_file> <phase>}"
OUTPUT="${3:?Usage: $0 <engine> <index> <output_file> <phase>}"
PHASE="${4:?Usage: $0 <engine> <index> <output_file> <phase>}"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
OS=$(uname)

if [ "$OS" = "Linux" ]; then
    # /usr/bin/time -v reports "Maximum resident set size (kbytes): N"
    TIME_OUTPUT=$( { /usr/bin/time -v "$ENGINE" "$INDEX" --bench-init; } 2>&1 )
    PEAK_KB=$(echo "$TIME_OUTPUT" \
        | grep "Maximum resident set size" \
        | awk '{print $NF}')

elif [ "$OS" = "Darwin" ]; then
    # \time -l reports RSS in bytes on the line containing "maximum resident set size"
    TIME_OUTPUT=$( { \time -l "$ENGINE" "$INDEX" --bench-init; } 2>&1 )
    PEAK_BYTES=$(echo "$TIME_OUTPUT" \
        | grep "maximum resident set size" \
        | awk '{print $1}')
    PEAK_KB=$(( PEAK_BYTES / 1024 ))

else
    echo "Unsupported OS: $OS" >&2
    exit 1
fi

if [ -z "${PEAK_KB:-}" ]; then
    echo "Error: could not parse peak RSS from time output" >&2
    echo "time output was:" >&2
    echo "$TIME_OUTPUT" >&2
    exit 1
fi

# Ensure output directory exists
mkdir -p "$(dirname "$OUTPUT")"

# Append JSON line to output file
cat >> "$OUTPUT" << EOF
{"phase": $PHASE, "timestamp": "$TIMESTAMP", "engine": "$ENGINE", "index": "$INDEX", "peak_rss_kb": $PEAK_KB}
EOF

echo "Peak RSS: ${PEAK_KB} KB"
echo "Written to: $OUTPUT"
