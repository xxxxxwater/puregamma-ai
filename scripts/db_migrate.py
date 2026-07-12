from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alembic import command

from packages.database.session import _alembic_config, _schema_gaps, upgrade_database


def main() -> None:
    parser = argparse.ArgumentParser(description="PureGamma database migration control")
    parser.add_argument("action", choices=("upgrade", "check", "current", "history"))
    parser.add_argument(
        "--no-adopt-existing",
        action="store_true",
        help="Fail instead of stamping an existing schema that exactly matches the baseline.",
    )
    args = parser.parse_args()
    if args.action == "upgrade":
        upgrade_database(allow_stamp_existing=not args.no_adopt_existing)
    elif args.action == "check":
        gaps = _schema_gaps()
        if gaps:
            raise SystemExit("Schema mismatch: " + "; ".join(gaps))
        print("Schema contains every current ORM table and column.")
    elif args.action == "current":
        command.current(_alembic_config(), verbose=True)
    else:
        command.history(_alembic_config(), verbose=True)


if __name__ == "__main__":
    main()
