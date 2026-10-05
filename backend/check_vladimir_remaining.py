# -*- coding: utf-8 -*-

import sqlite3
import json
from gulyay.geo import DgisGeoProvider

ids = (
    "vld002","vld009","vld016","vld017","vld028"
)

db = sqlite3.connect(r"data/gulyay.sqlite3")
geo = DgisGeoProvider()

for place_id in ids:
    row = db.execute("""
        SELECT name, search_aliases_json
        FROM places
        WHERE id = ?
    """, (place_id,)).fetchone()

    if not row:
        continue

    name, aliases_json = row
    aliases = json.loads(aliases_json or "[]")

    print("\n" + "=" * 100)
    print(place_id, name)

    for q in [name, *aliases]:
        query = f"{q}, Владимир"
        print("\nQUERY:", query)

        try:
            items = geo._places(
                q=query,
                locale="ru_RU",
                fields="items.point,items.name,items.full_name,items.address_name,items.type,items.rubrics",
                page_size=5,
                search_is_query_text_complete="true",
            )

            for i, item in enumerate(items[:5], 1):
                print(
                    i,
                    "ID=", item.get("id"),
                    "| NAME=", item.get("name"),
                    "| TYPE=", item.get("type"),
                    "| POINT=", item.get("point"),
                )

        except Exception as e:
            print("ERROR:", type(e).__name__, str(e))

db.close()
