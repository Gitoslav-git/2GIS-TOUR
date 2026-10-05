"""Small deterministic route-planning overrides, independent of providers."""

# Used only when the application has neither device location nor a textual start.
CITY_NO_GEO_START_OVERRIDES: dict[str, tuple[float, float]] = {
    "borovsk": (55.207583, 36.484355),  # Ploshchad Lenina
}
