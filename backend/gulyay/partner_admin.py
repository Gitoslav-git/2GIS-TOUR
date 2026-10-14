"""Operator-only partner brand discovery and confirmation commands."""
from __future__ import annotations

import argparse
import json

from .geo import CITY_NAMES, DgisGeoProvider
from .partners import PartnerRegistry


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Review and confirm 2GIS brand ids for partner candidates",
    )
    commands = result.add_subparsers(dest="command", required=True)
    discover = commands.add_parser("discover", help="print candidates; never saves an id")
    discover.add_argument("--city", choices=sorted(CITY_NAMES), default="moscow")
    discover.add_argument("--brand", help="local partner_brand_id; default is all pending rows")
    confirm = commands.add_parser("confirm", help="verify and persist one operator-selected id")
    confirm.add_argument("--city", choices=sorted(CITY_NAMES), required=True)
    confirm.add_argument("--brand", required=True)
    confirm.add_argument("--dgis-brand-id", required=True)
    commands.add_parser("list", help="show local registry without calling 2GIS")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    registry = PartnerRegistry()
    try:
        if args.command == "list":
            for brand in registry.list_brands():
                print(json.dumps(brand.__dict__, ensure_ascii=False, sort_keys=True))
            return 0
        provider = DgisGeoProvider()
        if args.command == "discover":
            brands = registry.list_brands(args.city)
            if args.brand:
                brands = [brand for brand in brands
                          if brand.partner_brand_id == args.brand]
            if not brands:
                raise SystemExit("Partner brand was not found in the local registry")
            for brand in brands:
                candidates = provider.discover_partner_brand_candidates(
                    args.city, brand.initial_search_q,
                )
                print(json.dumps({
                    "partner_brand_id": brand.partner_brand_id,
                    "brand_name": brand.brand_name,
                    "city_id": brand.city_id,
                    "candidates": [candidate.__dict__ for candidate in candidates],
                    "requires_manual_confirmation": True,
                }, ensure_ascii=False, sort_keys=True))
            return 0
        brand = registry.get_brand(args.brand, args.city)
        if brand is None:
            raise SystemExit("Partner brand was not found in the local registry")
        if not provider.verify_partner_brand_id(
                args.city, brand.initial_search_q, args.dgis_brand_id):
            raise SystemExit("2GIS brand id did not pass city/name verification; nothing saved")
        registry.confirm_brand_id(args.brand, args.city, args.dgis_brand_id)
        print(json.dumps({
            "partner_brand_id": args.brand,
            "city_id": args.city,
            "dgis_brand_id": args.dgis_brand_id,
            "dgis_id_status": "VERIFIED",
        }, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        registry.close()


if __name__ == "__main__":
    raise SystemExit(main())
