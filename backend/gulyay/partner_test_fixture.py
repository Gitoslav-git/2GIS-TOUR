"""Create or disable synthetic partner fixtures in an isolated test DB only."""
from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .geo import DgisGeoProvider
from .partners import PARTNER_BRANDS, PartnerRegistry


BRAND_IDS = tuple(row[0] for row in PARTNER_BRANDS)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--db-path", required=True)
    result.add_argument("--disable", action="store_true")
    selection = result.add_mutually_exclusive_group()
    selection.add_argument("--brand", choices=BRAND_IDS)
    selection.add_argument("--all", action="store_true")
    result.add_argument("--brand-id", action="append", default=[],
                        metavar="PARTNER_BRAND_ID=DGIS_BRAND_ID")
    # Backward-compatible single-Cofix form.
    result.add_argument("--dgis-brand-id")
    return result


def _brand_id_map(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        partner_id, separator, dgis_id = value.partition("=")
        if (not separator or partner_id not in BRAND_IDS or not dgis_id.strip()
                or partner_id in result):
            raise SystemExit("--brand-id must be a unique known PARTNER=DGIS value")
        result[partner_id] = dgis_id.strip()
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
        selected = list(BRAND_IDS) if args.all else [args.brand or "cofix"]
        if args.disable:
            for partner_id in selected:
                registry.set_brand_commercial_state(
                    partner_id, "moscow", "CANDIDATE", False, False,
                )
            print("Synthetic partner fixture disabled: " + ", ".join(selected))
            return 0
        supplied = _brand_id_map(args.brand_id)
        if args.dgis_brand_id:
            if len(selected) != 1 or supplied:
                raise SystemExit("--dgis-brand-id is only for one brand and cannot be combined")
            supplied[selected[0]] = args.dgis_brand_id
        missing = [partner_id for partner_id in selected if partner_id not in supplied]
        if missing:
            raise SystemExit("Missing --brand-id for: " + ", ".join(missing))
        provider = DgisGeoProvider()
        for partner_id in selected:
            brand = registry.get_brand(partner_id, "moscow")
            if brand is None or not provider.verify_partner_brand_id(
                    "moscow", brand.initial_search_q, supplied[partner_id]):
                raise SystemExit(f"{partner_id} brand id did not pass 2GIS verification")
        moscow = ZoneInfo("Europe/Moscow")
        for partner_id in selected:
            registry.confirm_brand_id(partner_id, "moscow", supplied[partner_id])
            registry.set_brand_commercial_state(
                partner_id, "moscow", "ACTIVE", True, True,
            )
            registry.save_offer(
                offer_id=f"test_{partner_id}_moscow_001",
                partner_brand_id=partner_id, city_id="moscow",
                title="Зайти по пути?",
                description=("Обычное посещение заведения. Скидки, бонусы и "
                             "промокоды не предусмотрены."),
                valid_from=datetime(2026, 10, 13, 0, 0, tzinfo=moscow),
                valid_until=datetime(2026, 12, 31, 23, 59, 59, tzinfo=moscow),
                timezone_name="Europe/Moscow", button_text="Добавить в маршрут",
                status="ACTIVE",
            )
        print(f"Synthetic partner fixture enabled only in {path}: "
              + ", ".join(selected))
        return 0
    finally:
        registry.close()


if __name__ == "__main__":
    raise SystemExit(main())
