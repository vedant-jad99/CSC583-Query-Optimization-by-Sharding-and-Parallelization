import argparse
import os
import sys

# ── Entry point ───────────────────────────────────────────────────────── #

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 Python Indexing Pipeline")
    parser.add_argument("--corpus", required=True, help="Path to corpus directory")
    parser.add_argument("--out", required=True, help="Output path for index.bin")
    args = parser.parse_args()

    if not os.path.isdir(args.corpus):
        print(f"Error: corpus directory '{args.corpus}' does not exist", file=sys.stderr)
        sys.exit(1)

    sorted_files: list[str] = presort_corpus(args.corpus)

    if not sorted_files:
        print(f"Error: no files found in corpus directory '{args.corpus}'", file=sys.stderr)
        sys.exit(1)

    print(f"Corpus: {len(sorted_files)} documents found in '{args.corpus}'")

    pipeline = Pipeline(file_slice=sorted_files, doc_id_offset=0)
    pipeline.run(output_path=args.out)

    print(f"Index written to '{args.out}'")


if __name__ == "__main__":
    main()

