"""CLI: ``python -m mcp_server.synth [--out DIR] [--seed N] [--config PATH]``."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from mcp_server.synth.generate import generate_extract, write_extract

CONFIG_PATH = Path(__file__).with_name("synth.yaml")
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "synthetic"
logger = logging.getLogger("synth")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the synthetic pupil and school extract.")
    parser.add_argument(
        "--out", type=Path, default=DATA_DIR, help="output directory (default mcp_server/data/synthetic)"
    )
    parser.add_argument("--seed", type=int, default=None, help="override the seed in synth.yaml")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="path to synth.yaml")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = yaml.safe_load(args.config.read_text())
    tables, manifest = generate_extract(cfg, seed=args.seed)
    for path in write_extract(tables, manifest, args.out):
        logger.info("wrote %s", path)
    logger.info("rows: %s", manifest["row_counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
