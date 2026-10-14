"""Create or disable the approved Cofix fixture in an isolated test DB only."""
from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .geo import DgisGeoProvider
from .partners import PartnerRegistry


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--db-path", required=True)
    result.add_argument("--disable", action="store_true")
    result.add_argument("--dgis-brand-id")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if os.getenv("GULYAY_ENV") != "test":
        raise SystemExit("Refusing fixture: set GULYAY_ENV=test explicitly")
    path = Path(args.db_path).expanduser().resolve()
    production_path = (Path(__file__).resolve().parent.parent
                       / "data" / "gulyay.sqlite3").resolve()
    if path == production_path:
        raise SystemExit("Refusing fixture: --db-path must not be the production DB")
    registry = PartnerRegistry(path)
    try:
        if args.disable:
            registry.set_brand_commercial_state(
                "cofix", "moscow", "CANDIDATE", False, False,
            )
            print("Synthetic Cofix fixture disabled")
            return 0
        if not args.dgis_brand_id:
            raise SystemExit("--dgis-brand-id is required when enabling the fixture")
        brand = registry.get_brand("cofix", "moscow")
        provider = DgisGeoProvider()
        if brand is None or not provider.verify_partner_brand_id(
                "moscow", brand.initial_search_q, args.dgis_brand_id):
            raise SystemExit("Cofix brand id did not pass 2GIS verification")
        registry.confirm_brand_id("cofix", "moscow", args.dgis_brand_id)
        registry.set_brand_commercial_state(
            "cofix", "moscow", "ACTIVE", True, True,
        )
        moscow = ZoneInfo("Europe/Moscow")
        registry.save_offer(
            offer_id="test_cofix_moscow_001", partner_brand_id="cofix",
            city_id="moscow", title="Зайти за кофе?",
            description=("Обычное посещение кофейни. Скидки, бонусы и "
                         "промокоды не предусмотрены."),
            valid_from=datetime(2026, 10, 13, 0, 0, tzinfo=moscow),
            valid_until=datetime(2026, 12, 31, 23, 59, 59, tzinfo=moscow),
            timezone_name="Europe/Moscow", button_text="Открыть в 2ГИС",
            status="ACTIVE",
        )
        print(f"Synthetic Cofix fixture enabled only in {path}")
        return 0
    finally:
        registry.close()


if __name__ == "__main__":
    raise SystemExit(main())
