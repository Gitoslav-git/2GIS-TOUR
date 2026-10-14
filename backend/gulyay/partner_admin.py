"""Operator-only partner brand discovery and confirmation commands."""
from __future__ import annotations

import argparse
import json

from .geo import CITY_NAMES, DgisGeoProvider
from .partners import PartnerRegistry


REFERENCE_BRANCHES = {
    "cofix": "70000001030037069",
    "surf": "70000001088173378",
    "drinkit": "70000001098497083",
    "oneprice": "70000001040199336",
    "thebull": "70000001062465220",
    "tanuki": "70000001058943800",
    "frank": "70000001046146813",
    "chaihona1": "4504127920024916",
    "syrovarnya": "70000001046169210",
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Review and confirm 2GIS brand ids for partner candidates",
    )
    commands = result.add_subparsers(dest="command", required=True)
    discover = commands.add_parser("discover", help="print candidates; never saves an id")
    discover.add_argument("--city", choices=sorted(CITY_NAMES), default="moscow")
    discover.add_argument("--brand", help="local partner_brand_id; default is all pending rows")
    preview = commands.add_parser(
        "preview-references", help="batch-resolve known branches; never changes the DB",
    )
    preview.add_argument("--city", choices=sorted(CITY_NAMES), default="moscow")
    preview.add_argument("--brand", choices=sorted(REFERENCE_BRANCHES))
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
        if not provider.places_key:
            raise SystemExit("DGIS_PLACES_API_KEY is not configured; database was not changed")
        if args.command == "preview-references":
            brands = registry.list_brands(args.city)
            if args.brand:
                brands = [brand for brand in brands
                          if brand.partner_brand_id == args.brand]
            references = {brand.partner_brand_id: REFERENCE_BRANCHES[brand.partner_brand_id]
                          for brand in brands if brand.partner_brand_id in REFERENCE_BRANCHES}
            resolved = provider.resolve_partner_brand_references(list(references.values()))
            center = provider.resolve_city_center(args.city)
            for brand in brands:
                place_id = references.get(brand.partner_brand_id)
                item = resolved.get(place_id or "")
                status, reason, branch_examples, branch_count = (
                    "NOT_FOUND", "reference branch was not returned", [], 0,
                )
                if item is not None:
                    if item.brand_count > 1:
                        status, reason = "AMBIGUOUS", "reference returned multiple items.brand values"
                    elif not item.dgis_brand_id:
                        status, reason = "AMBIGUOUS", "items.brand.id is absent; org.id was not substituted"
                    elif not provider.partner_reference_matches(
                            item, args.city, brand.initial_search_q):
                        status, reason = "AMBIGUOUS", "reference city or brand name did not match"
                    elif not provider.verify_partner_brand_id(
                            args.city, brand.initial_search_q, item.dgis_brand_id):
                        status, reason = "AMBIGUOUS", "brand_id search did not pass city/name verification"
                    else:
                        branches = provider.search_partner_branches(
                            args.city, item.dgis_brand_id, center,
                        )
                        other = [branch for branch in branches
                                 if branch.dgis_place_id != item.dgis_place_id]
                        if not other:
                            status, reason = "AMBIGUOUS", "brand_id search returned no other Moscow branches"
                        else:
                            status, reason = "VERIFIED_CANDIDATE", None
                            branch_count = len(branches)
                            branch_examples = [branch.dgis_place_id for branch in other[:3]]
                print(json.dumps({
                    "partner_brand_id": brand.partner_brand_id,
                    "reference_dgis_place_id": place_id,
                    "reference_place_name": None if item is None else item.place_name,
                    "dgis_brand_id": None if item is None else item.dgis_brand_id,
                    "brand_name": None if item is None else item.brand_name,
                    "dgis_org_id": None if item is None else item.dgis_org_id,
                    "city_alias": None if item is None else item.city_alias,
                    "status": status,
                    "other_branch_examples": branch_examples,
                    "found_branch_count": branch_count,
                    "reason": reason,
                    "database_changed": False,
                }, ensure_ascii=False, sort_keys=True))
            return 0
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
        if not registry.confirm_brand_id(args.brand, args.city, args.dgis_brand_id):
            raise SystemExit("Refusing to overwrite a different verified id; nothing saved")
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
