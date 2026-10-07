"""Map common agency niches to supported Google Places types."""

from __future__ import annotations


_TYPE_MAP = {
    "accountant": ("accounting",),
    "accountants": ("accounting",),
    "bakery": ("bakery",),
    "barber": ("hair_care",),
    "car dealer": ("car_dealer",),
    "car dealers": ("car_dealer",),
    "boutique": ("clothing_store",),
    "boutiques": ("clothing_store",),
    "clothing boutique": ("clothing_store",),
    "clothing boutiques": ("clothing_store",),
    "dentist": ("dentist",),
    "dentists": ("dentist",),
    "furniture shop": ("furniture_store",),
    "furniture shops": ("furniture_store",),
    "furniture store": ("furniture_store",),
    "furniture stores": ("furniture_store",),
    "gym": ("gym",),
    "gyms": ("gym",),
    "hotel": ("hotel",),
    "hotels": ("hotel",),
    "lawyer": ("lawyer",),
    "lawyers": ("lawyer",),
    "pharmacy": ("pharmacy",),
    "pharmacies": ("pharmacy",),
    "plumber": ("plumber",),
    "plumbers": ("plumber",),
    "real estate": ("real_estate_agency",),
    "real estate agency": ("real_estate_agency",),
    "real estate agencies": ("real_estate_agency",),
    "realtor": ("real_estate_agency",),
    "realtors": ("real_estate_agency",),
    "restaurant": ("restaurant",),
    "restaurants": ("restaurant",),
    "shoe store": ("shoe_store",),
    "shoe stores": ("shoe_store",),
    "spa": ("spa",),
    "spas": ("spa",),
    "veterinarian": ("veterinary_care",),
    "veterinarians": ("veterinary_care",),
}


def supported_place_types(niche: str) -> tuple[str, ...] | None:
    """Return exact supported Google types, or None for free-form niches."""
    return _TYPE_MAP.get(" ".join(niche.casefold().split()))