#!/bin/bash
##############################################################
#
# bench_memory.sh
# ───────────────
# Measures peak resident set size (RSS) of the C++ engine
# during initialization using /usr/bin/time (Linux/macOS).
#
# Usage:
#   Phase 1:
#     bash benchmark/bench_memory.sh <engine> <index> <output> <phase>
#
#   Phase 2/3:
#     bash benchmark/bench_memory.sh <engine> <shards/> <output> <phase> \
#       --shards 4
#
# Output:
#   Appends a JSON line to <output_file>:
#   {"phase": N, "timestamp": "...", "peak_rss_kb": N}
#
# Notes:
#   - Measures init-only mode (--bench-init flag)
#   - Run once per benchmark session (memory is deterministic)
#   - On macOS, RSS is reported in bytes; converted to KB here
#   - Extra args after <phase> are forwarded to the engine binary
#
# Author: Vedant Keshav Jadhav
# Phase:  1, 2, 3 (portable)
#
##############################################################

set -eo pipefail

ENGINE="${1:?Usage: $0 <engine> <index> <output_file> <phase> [engine_args...]}"
INDEX="${2:?Usage: $0 <engine> <index> <output_file> <phase> [engine_args...]}"
OUTPUT="${3:?Usage: $0 <engine> <index> <output_file> <phase> [engine_args...]}"
PHASE="${4:?Usage: $0 <engine> <index> <output_file> <phase> [engine_args...]}"

# Any remaining args forwarded to the engine (e.g. --shards 4
shift 4
EXTRA_ARGS=("${@}")

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
OS=$(uname)

if [ "$OS" = "Linux" ]; then
    TIME_OUTPUT=$( { /usr/bin/time -v "$ENGINE" "$INDEX" --bench-init "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"; } 2>&1 )
    PEAK_KB=$(echo "$TIME_OUTPUT" \
        | grep "Maximum resident set size" \
        | awk '{print $NF}')

elif [ "$OS" = "Darwin" ]; then
    TIME_OUTPUT=$( { /usr/bin/time -l "$ENGINE" "$INDEX" --bench-init "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"; } 2>&1 )
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

mkdir -p "$(dirname "$OUTPUT")"

cat >> "$OUTPUT" << EOF
{"phase": $PHASE, "timestamp": "$TIMESTAMP", "engine": "$ENGINE", "index": "$INDEX", "peak_rss_kb": $PEAK_KB}
EOF

echo "Peak RSS: ${PEAK_KB} KB"
echo "Written to: $OUTPUT"
