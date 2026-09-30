"""Deterministic visit-duration classification for 2GIS candidates."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import PlaceCandidate


class VisitCategory(StrEnum):
    MONUMENT="MONUMENT"; SCULPTURE_ART_OBJECT="SCULPTURE_ART_OBJECT"; HISTORIC_BUILDING="HISTORIC_BUILDING"; SQUARE="SQUARE"; VIEWPOINT="VIEWPOINT"; OBSERVATION_TOWER="OBSERVATION_TOWER"
    SMALL_PARK="SMALL_PARK"; PARK="PARK"; LARGE_PARK="LARGE_PARK"; BOTANICAL_GARDEN="BOTANICAL_GARDEN"; EMBANKMENT="EMBANKMENT"; PEDESTRIAN_STREET="PEDESTRIAN_STREET"; HISTORIC_AREA="HISTORIC_AREA"
    SMALL_MUSEUM="SMALL_MUSEUM"; MUSEUM="MUSEUM"; LARGE_MUSEUM="LARGE_MUSEUM"; GALLERY="GALLERY"; EXHIBITION="EXHIBITION"; SCIENCE_INTERACTIVE_MUSEUM="SCIENCE_INTERACTIVE_MUSEUM"
    TEMPLE="TEMPLE"; CATHEDRAL="CATHEDRAL"; MONASTERY="MONASTERY"; PALACE_MANOR="PALACE_MANOR"; FORTRESS_KREMLIN="FORTRESS_KREMLIN"
    ARCHAEOLOGICAL_SITE="ARCHAEOLOGICAL_SITE"; BUNKER_MILITARY_SITE="BUNKER_MILITARY_SITE"; INDUSTRIAL_HERITAGE="INDUSTRIAL_HERITAGE"; STREET_ART_AREA="STREET_ART_AREA"; CREATIVE_CLUSTER="CREATIVE_CLUSTER"
    MARKET="MARKET"; GASTRO_MARKET="GASTRO_MARKET"; SHOPPING_GALLERY="SHOPPING_GALLERY"; FLEA_MARKET="FLEA_MARKET"
    CAFE="CAFE"; COFFEE_DESSERT="COFFEE_DESSERT"; FAST_FOOD="FAST_FOOD"; RESTAURANT="RESTAURANT"; BAR_PUB="BAR_PUB"; FOOD_HALL="FOOD_HALL"
    BEACH_SHORT="BEACH_SHORT"; BEACH_RECREATION="BEACH_RECREATION"; LAKE_POND="LAKE_POND"; WATERFALL="WATERFALL"; NATURAL_LANDMARK="NATURAL_LANDMARK"; NATURE_PARK="NATURE_PARK"; ECO_TRAIL="ECO_TRAIL"
    ZOO_SMALL="ZOO_SMALL"; ZOO="ZOO"; AQUARIUM="AQUARIUM"; FARM="FARM"; PLANETARIUM="PLANETARIUM"; ENTERTAINMENT_CENTER="ENTERTAINMENT_CENTER"; AMUSEMENT_PARK="AMUSEMENT_PARK"; FESTIVAL_EVENT_AREA="FESTIVAL_EVENT_AREA"
    ROOFTOP="ROOFTOP"; NECROPOLIS="NECROPOLIS"; MEMORIAL_COMPLEX="MEMORIAL_COMPLEX"; PHOTO_SPOT="PHOTO_SPOT"
    GENERIC_ATTRACTION="GENERIC_ATTRACTION"; GENERIC_PLACE="GENERIC_PLACE"; GENERIC_BRANCH="GENERIC_BRANCH"


@dataclass(frozen=True)
class VisitProfile:
    minimum: int
    default: int
    maximum: int


_PROFILE_ROWS = {
    "MONUMENT":(10,20,30), "SCULPTURE_ART_OBJECT":(10,15,25), "HISTORIC_BUILDING":(15,30,45), "SQUARE":(15,25,40), "VIEWPOINT":(15,25,40), "OBSERVATION_TOWER":(20,30,45),
    "SMALL_PARK":(20,35,50), "PARK":(30,50,75), "LARGE_PARK":(45,75,120), "BOTANICAL_GARDEN":(45,75,120), "EMBANKMENT":(25,45,75), "PEDESTRIAN_STREET":(25,45,75), "HISTORIC_AREA":(40,60,100),
    "SMALL_MUSEUM":(35,50,70), "MUSEUM":(45,75,105), "LARGE_MUSEUM":(75,105,150), "GALLERY":(35,55,80), "EXHIBITION":(40,60,90), "SCIENCE_INTERACTIVE_MUSEUM":(60,90,120),
    "TEMPLE":(15,25,40), "CATHEDRAL":(20,35,50), "MONASTERY":(35,60,90), "PALACE_MANOR":(40,60,90), "FORTRESS_KREMLIN":(45,75,120),
    "ARCHAEOLOGICAL_SITE":(25,45,70), "BUNKER_MILITARY_SITE":(40,60,90), "INDUSTRIAL_HERITAGE":(30,50,80), "STREET_ART_AREA":(20,40,60), "CREATIVE_CLUSTER":(35,60,90),
    "MARKET":(30,50,75), "GASTRO_MARKET":(40,60,90), "SHOPPING_GALLERY":(25,40,60), "FLEA_MARKET":(35,55,80),
    "CAFE":(25,40,55), "COFFEE_DESSERT":(20,30,45), "FAST_FOOD":(20,30,45), "RESTAURANT":(50,70,95), "BAR_PUB":(40,60,90), "FOOD_HALL":(35,55,80),
    "BEACH_SHORT":(25,45,60), "BEACH_RECREATION":(60,90,120), "LAKE_POND":(20,35,55), "WATERFALL":(20,35,50), "NATURAL_LANDMARK":(30,50,75), "NATURE_PARK":(45,75,120), "ECO_TRAIL":(45,75,120),
    "ZOO_SMALL":(60,90,120), "ZOO":(90,120,180), "AQUARIUM":(60,80,110), "FARM":(50,75,105), "PLANETARIUM":(60,80,100), "ENTERTAINMENT_CENTER":(60,90,120), "AMUSEMENT_PARK":(90,150,240), "FESTIVAL_EVENT_AREA":(45,60,90),
    "ROOFTOP":(25,40,60), "NECROPOLIS":(30,50,75), "MEMORIAL_COMPLEX":(25,45,70), "PHOTO_SPOT":(5,15,25),
    "GENERIC_ATTRACTION":(20,40,60), "GENERIC_PLACE":(25,45,75), "GENERIC_BRANCH":(30,40,60),
}
VISIT_PROFILES = {VisitCategory(name): VisitProfile(*values) for name, values in _PROFILE_ROWS.items()}


def _text(candidate: PlaceCandidate) -> tuple[str, str]:
    name = candidate.name.casefold().replace("ё", "е").strip()
    rubrics = " ".join(candidate.rubrics).casefold().replace("ё", "е").strip()
    return name, rubrics


def _has(text: str, *words: str) -> bool:
    return any(word in text for word in words)


def classify_visit_category(candidate: PlaceCandidate) -> VisitCategory:
    """Classify by food, rubric, provider type, then name; no LLM or fuzzy match."""
    name, rubrics = _text(candidate)
    combined = f"{rubrics} {name}"
    provider_type = candidate.providerType.casefold()

    # Food wins over names such as "Кафе Музей".
    if candidate.isFood or _has(rubrics, "кафе", "ресторан", "кофейн", "бар", "фаст", "фуд"):
        if _has(rubrics, "гастромаркет", "фуд-маркет"): return VisitCategory.GASTRO_MARKET
        if _has(rubrics, "фуд-хол", "фудкорт", "food hall"): return VisitCategory.FOOD_HALL
        if _has(rubrics, "кофейн", "кондитер", "десерт"): return VisitCategory.COFFEE_DESSERT
        if _has(rubrics, "быстрое питание", "фастфуд") or _has(name, "бургер", "шаурм", "пицц"): return VisitCategory.FAST_FOOD
        if _has(rubrics, "бар", "паб"): return VisitCategory.BAR_PUB
        if _has(rubrics, "ресторан"): return VisitCategory.RESTAURANT
        return VisitCategory.CAFE

    # A precise name may refine a broad museum/park rubric; it never overrides
    # an unrelated rubric such as a hotel or ordinary building.
    if _has(rubrics, "музе"):
        if _has(name, "дом-музей"): return VisitCategory.SMALL_MUSEUM
        if _has(name, "государственн", "музей-заповедник", "музейный комплекс"):
            return VisitCategory.LARGE_MUSEUM
    if _has(rubrics, "парк") and _has(name, "лесопарк", "парк культуры"):
        return VisitCategory.LARGE_PARK

    # Rubrics are deliberately considered before the object's name.
    rules = (
        (VisitCategory.MONASTERY, ("монастыр",)), (VisitCategory.CATHEDRAL, ("собор",)),
        (VisitCategory.TEMPLE, ("храм", "церков", "мечеть", "синагог")),
        (VisitCategory.FORTRESS_KREMLIN, ("кремл", "крепост", "цитадел")),
        (VisitCategory.BOTANICAL_GARDEN, ("ботаничес", "дендрар")), (VisitCategory.LARGE_PARK, ("лесопарк", "парк культуры")),
        (VisitCategory.SMALL_PARK, ("сквер",)), (VisitCategory.EMBANKMENT, ("набереж",)),
        (VisitCategory.VIEWPOINT, ("смотров", "обзорн")), (VisitCategory.ECO_TRAIL, ("экотроп", "экологическ маршрут")),
        (VisitCategory.ZOO_SMALL, ("контактный зоопарк",)), (VisitCategory.ZOO, ("зоопарк",)),
        (VisitCategory.AQUARIUM, ("океанари", "аквариум")), (VisitCategory.PLANETARIUM, ("планетар",)),
        (VisitCategory.GALLERY, ("галере",)), (VisitCategory.EXHIBITION, ("выставоч",)),
        (VisitCategory.SCIENCE_INTERACTIVE_MUSEUM, ("интерактив", "научн")),
        (VisitCategory.LARGE_MUSEUM, ("государственн музей", "музей-заповедник", "музейный комплекс")),
        (VisitCategory.SMALL_MUSEUM, ("дом-музей",)), (VisitCategory.MUSEUM, ("музе",)),
        (VisitCategory.MEMORIAL_COMPLEX, ("мемориальн комплекс",)), (VisitCategory.MONUMENT, ("памятник", "монумент")),
        (VisitCategory.SCULPTURE_ART_OBJECT, ("скульптур", "арт-объект", "инсталляц")),
        (VisitCategory.PALACE_MANOR, ("дворец", "усадьб")), (VisitCategory.STREET_ART_AREA, ("стрит-арт", "граффити")),
        (VisitCategory.CREATIVE_CLUSTER, ("арт-кластер", "творческ кластер", "арт-пространств")),
        (VisitCategory.FLEA_MARKET, ("блошин", "антикварн рынок")), (VisitCategory.MARKET, ("рынок", "ярмарк")),
        (VisitCategory.BEACH_RECREATION, ("пляжный комплекс", "пляж отдыха")), (VisitCategory.BEACH_SHORT, ("пляж",)),
        (VisitCategory.LAKE_POND, ("озер", "пруд")), (VisitCategory.WATERFALL, ("водопад",)),
        (VisitCategory.ROOFTOP, ("руфтоп", "смотровая крыша")), (VisitCategory.NECROPOLIS, ("некропол",)),
        (VisitCategory.PEDESTRIAN_STREET, ("пешеходн улиц",)), (VisitCategory.SQUARE, ("площад",)),
        (VisitCategory.PARK, ("парк", "сад")),
    )
    for category, words in rules:
        if _has(rubrics, *words): return category

    # Name signals are safe only for a tourist provider type or a tourist rubric.
    tourist = provider_type in {"attraction", "adm_div.place", "street"} or _has(rubrics, "достопримеч", "культур", "истор")
    if tourist:
        for category, words in rules:
            if _has(name, *words): return category
        if _has(name, "башн", "колокольн"): return VisitCategory.OBSERVATION_TOWER
        if _has(name, "историческ квартал", "старый город"): return VisitCategory.HISTORIC_AREA
        if _has(name, "особняк", "историческ здание"): return VisitCategory.HISTORIC_BUILDING
    if provider_type == "attraction": return VisitCategory.GENERIC_ATTRACTION
    if provider_type == "adm_div.place": return VisitCategory.GENERIC_PLACE
    return VisitCategory.GENERIC_BRANCH


def visit_minutes(candidate: PlaceCandidate, pace: str) -> int:
    profile = VISIT_PROFILES[classify_visit_category(candidate)]
    if pace == "INTENSIVE": return profile.minimum
    if pace == "RELAXED": return profile.maximum
    return profile.default


def minimum_visit_minutes(candidate: PlaceCandidate) -> int:
    return VISIT_PROFILES[classify_visit_category(candidate)].minimum
