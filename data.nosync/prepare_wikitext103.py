"""
prepare_wikitext103.py
──────────────────────
Downloads WikiText-103 train split and writes each non-empty,
non-header line as an individual document file.

Output: ~1.8M files in <out_dir>/
        doc_0000000.txt, doc_0000001.txt, ...

Usage:
    pip install datasets
    python3 prepare_wikitext103.py --out-dir data/corpus

    # Limit to first N docs for testing
    python3 prepare_wikitext103.py --out-dir data/corpus --limit 100000

Runtime:  ~5–15 minutes depending on download speed and disk.
Disk:     ~2–3 GB for the full 1.8M files.

Author: Vedant Keshav Jadhav
"""

import argparse
import os
import sys
import time


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prepare WikiText-103 corpus")
    p.add_argument(
        "--out-dir",
        required=True,
        help="Directory to write document files into"
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after writing this many documents (default: all ~1.8M)"
    )
    p.add_argument(
        "--split",
        default="train",
        choices=["train", "validation", "test"],
        help="Dataset split to use (default: train)"
    )
    return p.parse_args()


def check_dependencies() -> None:
    try:
        import datasets  # noqa: F401
    except ImportError:
        print("Error: 'datasets' package not installed.", file=sys.stderr)
        print("Run: pip install datasets", file=sys.stderr)
        sys.exit(1)


def is_header(line: str) -> bool:
    """
    WikiText-103 uses = markers for article and section headings.
    = Title =          article heading
    = = Section = =    section heading
    Skip both.
    """
    stripped = line.strip()
    return stripped.startswith("=") and stripped.endswith("=")


def main() -> None:
    args = parse_args()
    check_dependencies()

    from datasets import load_dataset

    os.makedirs(args.out_dir, exist_ok=True)

    print(f"Downloading WikiText-103 ({args.split} split)...")
    print("This may take a few minutes on first run (183MB download).\n")

    dataset = load_dataset(
        "Salesforce/wikitext",
        "wikitext-103-raw-v1",
        split=args.split,
        trust_remote_code=False,
    )

    total_rows = len(dataset)
    limit      = args.limit if args.limit else total_rows

    print(f"Total rows in split: {total_rows:,}")
    print(f"Writing up to {limit:,} documents to: {args.out_dir}\n")

    doc_id    = 0
    skipped   = 0
    t0        = time.perf_counter()
    report_at = 100_000  # print progress every 100K docs

    for row in dataset:
        if doc_id >= limit:
            break

        line = row["text"]

        # Skip empty lines and article/section headers
        if not line or not line.strip() or is_header(line):
            skipped += 1
            continue

        path = os.path.join(args.out_dir, f"doc_{doc_id:07d}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(line.strip())

        doc_id += 1

        if doc_id % report_at == 0:
            elapsed = time.perf_counter() - t0
            rate    = doc_id / elapsed
            eta     = (limit - doc_id) / rate if rate > 0 else 0
            print(f"  {doc_id:>9,} documents written  "
                  f"({rate:,.0f} docs/s  ETA: {eta:.0f}s)")

    elapsed = time.perf_counter() - t0
    print(f"\nDone.")
    print(f"  Documents written: {doc_id:,}")
    print(f"  Rows skipped:      {skipped:,}  (empty + headers)")
    print(f"  Output directory:  {args.out_dir}")
    print(f"  Total time:        {elapsed:.1f}s  ({doc_id/elapsed:,.0f} docs/s)")

    # Disk usage
    total_bytes = sum(
        os.path.getsize(os.path.join(args.out_dir, f))
        for f in os.listdir(args.out_dir)
        if f.endswith(".txt")
    )
    print(f"  Total size:        {total_bytes / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
