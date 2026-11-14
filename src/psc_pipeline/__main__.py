"""Entry point: python -m psc_pipeline --input <snapshot> [--dry-run]."""
import argparse
import os
import sys


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="psc_pipeline", description=__doc__)
    p.add_argument("--input", required=True, help="path to the snapshot (.txt.gz or .txt)")
    p.add_argument("--dry-run", action="store_true",
                   default=os.environ.get("PSC_DRY_RUN", "").lower() == "true",
                   help="run every check but write nothing (or PSC_DRY_RUN=true)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    print(f"psc_pipeline: not implemented yet (input={args.input}, dry_run={args.dry_run})", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
