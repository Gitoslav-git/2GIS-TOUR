# -*- coding: utf-8 -*-

from gulyay.geo import DgisGeoProvider

geo = DgisGeoProvider()

queries = [
    "Парк Царицыно, Москва",
    "Царицыно, Москва",
    "Государственный музей-заповедник Царицыно, Москва",
]

for q in queries:
    print()
    print("=" * 80)
    print("QUERY:", q)

    try:
        items = geo._places(
            q=q,
            locale="ru_RU",
            fields="items.point,items.name,items.full_name,items.address_name,items.type,items.rubrics",
            page_size=10,
            search_is_query_text_complete="true",
        )

        print("COUNT:", len(items))

        for i, item in enumerate(items, 1):
            print(
                i,
                "ID=", item.get("id"),
                "| NAME=", item.get("name"),
                "| FULL=", item.get("full_name"),
                "| TYPE=", item.get("type"),
                "| POINT=", item.get("point"),
            )

    except Exception as e:
        print("ERROR:", type(e).__name__, str(e))
