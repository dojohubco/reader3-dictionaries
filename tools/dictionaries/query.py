#!/usr/bin/env python3
"""Print a dictionary popup without opening the database for writing."""

import argparse
import sqlite3
import sys
from pathlib import Path

# -I omits the script directory; only add our explicitly resolved sibling modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dictionary import DATABASE, connect, render


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text")
    parser.add_argument("--lang", choices=("en", "ka"), default="en")
    parser.add_argument("--db", type=Path, default=DATABASE)
    args = parser.parse_args()
    try:
        with connect(args.db) as db:
            print(render(db, args.text, args.lang))
    except sqlite3.Error as error:
        parser.exit(1, f"Dictionary unavailable: {error}\nRun python3 -I tools/dictionaries/build.py first.\n")


if __name__ == "__main__":
    main()
