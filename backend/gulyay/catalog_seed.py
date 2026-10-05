"""Import and offline-enrich local place catalogue seeds.

Usage:
    python -m gulyay.catalog_seed
    python -m gulyay.catalog_seed --resolve-missing --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .catalog import CatalogImportError, CatalogPlace, PlaceCatalog, bundled_seed_path
from .geo import DgisGeoProvider, GeoPlaceNotFound, GeoUnavailable


LOGGER = logging.getLogger("gulyay.catalog_seed")


@dataclass(frozen=True)
class EnrichmentReport:
    resolved_provider: list[CatalogPlace]
    resolved_coords_only: list[CatalogPlace]
    unresolved: list[CatalogPlace]


def resolve_missing(catalog: PlaceCatalog, geo: DgisGeoProvider, *,
                    city_id: str | None = None, dry_run: bool = False) -> EnrichmentReport:
    for place in catalog.unresolved(city_id):
        try:
            by_id = getattr(geo, "resolve_catalog_place_by_id", None)
            # A confirmed provider ID is stronger than another fuzzy name
            # search. Use it whenever that row still needs any enrichment so
            # coordinates and provider_name cannot come from a different item.
            if place.dgis_place_id and callable(by_id):
                selected = by_id(place.city_id, place.dgis_place_id)
            else:
                selected = geo.resolve_catalog_place(
                    place.city_id, place.name, place.search_aliases,
                )
        except (GeoUnavailable, GeoPlaceNotFound) as exc:
            LOGGER.warning(
                "Catalog enrichment provider error: catalog_id=%s city_id=%s error=%s",
                place.id, place.city_id, type(exc).__name__,
            )
            continue
        if selected is None:
            continue
        if not dry_run:
            catalog.update_resolution(
                place.id, selected.dgis_place_id, selected.provider_name,
                selected.lat, selected.lon,
            )
    provider, coords_only, unresolved = catalog.enrichment_groups(city_id)
    return EnrichmentReport(provider, coords_only, unresolved)


def _load_overrides(path: Path) -> dict[str, dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogImportError(f"Не удалось прочитать overrides: {path}") from exc
    if not isinstance(payload, dict):
        raise CatalogImportError("Overrides должны быть JSON-объектом id -> поля")
    return payload


def print_report(report: EnrichmentReport, *, dry_run: bool = False) -> None:
    prefix = "DRY-RUN " if dry_run else ""
    groups = (
        ("RESOLVED_PROVIDER", report.resolved_provider),
        ("RESOLVED_COORDS_ONLY", report.resolved_coords_only),
        ("UNRESOLVED", report.unresolved),
    )
    for label, places in groups:
        print(f"{prefix}{label} ({len(places)})")
        for place in places:
            provider = f" -> {place.provider_name}" if place.provider_name else ""
            provider_id = f" [{place.dgis_place_id}]" if place.dgis_place_id else ""
            print(f"  {place.id}: {place.name}{provider}{provider_id}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Import/enrich the Гуляй place catalogue")
    result.add_argument("--seed", type=Path, default=bundled_seed_path())
    result.add_argument("--db", type=Path, default=None)
    result.add_argument("--city", default=None)
    result.add_argument(
        "--overrides", type=Path, default=None,
        help="JSON manual overrides: catalog id -> lat/lon/dgis_place_id/provider_name",
    )
    result.add_argument("--resolve-missing", action="store_true")
    result.add_argument("--dry-run", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    # A dry-run imports into memory, so validation and resolution cannot mutate
    # either the production database or an already enriched catalogue.
    catalog = PlaceCatalog(":memory:" if args.dry_run else args.db)
    try:
        count = catalog.import_seed(args.seed, dry_run=False)
        print(f"{'DRY-RUN ' if args.dry_run else ''}VALIDATED {count} catalogue rows")
        if args.overrides:
            applied = catalog.apply_manual_overrides(_load_overrides(args.overrides))
            print(f"{'DRY-RUN ' if args.dry_run else ''}APPLIED_OVERRIDES {applied}")
        if not args.resolve_missing:
            return 0
        geo = DgisGeoProvider()
        geo.ensure_configured()
        report = resolve_missing(
            catalog, geo, city_id=args.city,
            # --dry-run already uses an isolated in-memory catalogue. Updating
            # it makes the final grouped report accurately preview the result.
            dry_run=False,
        )
        print_report(report, dry_run=args.dry_run)
        return 0
    finally:
        catalog.close()


if __name__ == "__main__":
    raise SystemExit(main())
