from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from engine.pipeline import run_pipeline
except ModuleNotFoundError:  # pragma: no cover - path fallback
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from engine.pipeline import run_pipeline


def default_output_dir(pdf_path: Path) -> Path:
    root = Path.cwd()
    analysis_dir = root / "analysis" / "engine_runs"
    return analysis_dir / pdf_path.stem


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Budget PDF extraction engine")
    parser.add_argument("--input", required=True, help="Path to input PDF")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for artifacts and output.json",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite contents in the output directory",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pdf_path = Path(args.input).expanduser().resolve()
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else default_output_dir(pdf_path)
    )

    output_path = run_pipeline(pdf_path, output_dir, overwrite=args.overwrite)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
