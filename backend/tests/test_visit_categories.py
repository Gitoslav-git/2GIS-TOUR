import pytest

from gulyay.models import PlaceCandidate
from gulyay.visit_categories import VisitCategory, classify_visit_category, visit_minutes


def place(name="Место", rubrics=(), provider_type="attraction", food=False):
    return PlaceCandidate(placeId="p", name=name, lat=54.19, lon=37.61,
                          rubrics=list(rubrics), schedule={}, isFood=food,
                          providerType=provider_type)


@pytest.mark.parametrize(("candidate", "expected"), [
    (place("Городской музей", ["Музеи"]), VisitCategory.MUSEUM),
    (place("Дом-музей Чехова", ["Музеи"]), VisitCategory.SMALL_MUSEUM),
    (place("Государственный музей", ["Музеи"]), VisitCategory.LARGE_MUSEUM),
    (place("Галерея", ["Галереи"]), VisitCategory.GALLERY),
    (place("Памятник", ["Памятники"]), VisitCategory.MONUMENT),
    (place("Скульптура", ["Арт-объекты"]), VisitCategory.SCULPTURE_ART_OBJECT),
    (place("Парк", ["Парки"]), VisitCategory.PARK),
    (place("Сквер", ["Скверы"]), VisitCategory.SMALL_PARK),
    (place("Лесопарк", ["Парки"]), VisitCategory.LARGE_PARK),
    (place("Набережная", ["Набережные"]), VisitCategory.EMBANKMENT),
    (place("Храм", ["Храмы"]), VisitCategory.TEMPLE),
    (place("Собор", ["Соборы"]), VisitCategory.CATHEDRAL),
    (place("Монастырь", ["Монастыри"]), VisitCategory.MONASTERY),
    (place("Кремль", ["Достопримечательности"]), VisitCategory.FORTRESS_KREMLIN),
    (place("Ресторан", ["Рестораны"], food=True), VisitCategory.RESTAURANT),
    (place("Кафе", ["Кафе"], food=True), VisitCategory.CAFE),
    (place("Кофейня", ["Кофейни"], food=True), VisitCategory.COFFEE_DESSERT),
    (place("Бургерная", ["Быстрое питание"], food=True), VisitCategory.FAST_FOOD),
    (place("Гастромаркет", ["Гастромаркеты"], food=True), VisitCategory.GASTRO_MARKET),
    (place("Зоопарк", ["Зоопарки"]), VisitCategory.ZOO),
    (place("Океанариум", ["Океанариумы"]), VisitCategory.AQUARIUM),
    (place("Неизвестный объект", [], "attraction"), VisitCategory.GENERIC_ATTRACTION),
    (place("Неизвестная территория", [], "adm_div.place"), VisitCategory.GENERIC_PLACE),
    (place("Туристический центр", [], "branch"), VisitCategory.GENERIC_BRANCH),
])
def test_classifies_representative_places(candidate, expected):
    assert classify_visit_category(candidate) is expected


def test_food_rubric_wins_over_museum_word_in_name():
    assert classify_visit_category(place("Кафе Музей", ["Кафе"], "branch", True)) is VisitCategory.CAFE


def test_building_without_tourist_signal_is_not_historic_building():
    assert classify_visit_category(place("Жилой дом", [], "building")) is VisitCategory.GENERIC_BRANCH


@pytest.mark.parametrize(("pace", "expected"), [
    ("INTENSIVE", 45), ("NORMAL", 75), ("RELAXED", 105),
])
def test_museum_pace_selects_profile_values_without_multiplier(pace, expected):
    assert visit_minutes(place("Музей", ["Музеи"]), pace) == expected
