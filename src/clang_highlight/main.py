import clang_highlight
import argparse
import sys
from pathlib import Path

from .output import FORMATTERS


def main():
    parser = argparse.ArgumentParser("clang-highlight")
    parser.add_argument(
        "-p",
        type=Path,
        help="Build path (which contains compile_commands.json",
        metavar="PATH",
    )
    parser.add_argument(
        "--format",
        "-f",
        type=str,
        help="Output format",
        choices=FORMATTERS.keys(),
        default="html",
    )
    parser.add_argument("--cppref", action=argparse.BooleanOptionalAction)
    parser.add_argument("file", type=Path, help="Source file")

    args = parser.parse_args()

    highlighted = clang_highlight.run(
        filename=args.file, build_dir=args.p, cppref=args.cppref
    )

    formatter = FORMATTERS[args.format]
    formatter(highlighted, sys.stdout)
