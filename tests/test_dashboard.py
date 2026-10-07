"""Tests for dashboard filtering, metrics, and download serialization."""

from __future__ import annotations

import json
import unittest

from app.dashboard import (
    TABLE_COLUMNS,
    businesses_csv,
    businesses_frame,
    businesses_json,
    competitor_snapshot,
    filter_businesses,
    summary_metrics,
)
from app.models import Business
from app.utils.place_types import supported_place_types


def make_business(
    place_id: str,
    *,
    website: str | None,
    rating: float | None,
    reviews: int,
) -> Business:
    return Business(
        name=f"Business {place_id}",
        address="Hyderabad",
        rating=rating,
        reviews_count=reviews,
        website=website,
        phone=None,
        maps_url=None,
        place_id=place_id,
    )


class DashboardHelpersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.businesses = [
            make_business("a", website=None, rating=4.5, reviews=40),
            make_business("b", website="https://b.example", rating=3.5, reviews=10),
            make_business("c", website=None, rating=None, reviews=90),
        ]

    def test_table_has_requested_display_columns_and_status(self) -> None:
        frame = businesses_frame(self.businesses)

        self.assertEqual(frame.columns[: len(TABLE_COLUMNS)].tolist(), TABLE_COLUMNS)
        self.assertEqual(frame["Website Status"].tolist(), ["No Website", "Has Website", "No Website"])
        self.assertIn("Opportunity Score", frame.columns)
        self.assertIn("Opportunity Label", frame.columns)
        self.assertIn("Lead Score", frame.columns)

    def test_filters_for_high_opportunity_and_thresholds(self) -> None:
        result = filter_businesses(
            self.businesses,
            high_opportunity_only=True,
            minimum_rating=4.0,
            minimum_reviews=20,
        )

        self.assertEqual([business.place_id for business in result], ["a"])

    def test_summary_counts_no_website_as_high_opportunity(self) -> None:
        self.assertEqual(
            summary_metrics(self.businesses),
            {
                "total": 3,
                "with_website": 1,
                "without_website": 2,
                "average_rating": 4.0,
                "best_leads": 0,
            },
        )

    def test_csv_and_json_download_data(self) -> None:
        csv_data = businesses_csv(self.businesses).decode("utf-8-sig")
        json_data = json.loads(businesses_json(self.businesses))

        self.assertIn("Business Name,Rating,Reviews", csv_data)
        self.assertEqual(json_data[0]["Website Status"], "No Website")
        self.assertNotIn("place_id", json_data[0])
        self.assertIn("Opportunity Score", json_data[0])
        self.assertIn("Opportunity Label", json_data[0])
        self.assertIn("Lead Score", json_data[0])

    def test_audit_fields_are_exported_only_when_available(self) -> None:
        unaudited = json.loads(businesses_json([self.businesses[0]]))
        audited = json.loads(
            businesses_json(
                [self.businesses[0]],
                {"a": {"website_audit_score": 4, "website_audit_grade": "Poor"}},
            )
        )

        self.assertNotIn("website_audit_score", unaudited[0])
        self.assertEqual(audited[0]["website_audit_score"], 4)
        self.assertIn(b"website_audit_score", businesses_csv([self.businesses[0]], {
            "a": {"website_audit_score": 4}
        }))

    def test_hot_high_and_no_website_filters_and_sorts(self) -> None:
        hot = make_business("hot", website=None, rating=4.5, reviews=100)
        high = make_business("high", website=None, rating=4.5, reviews=0)
        no_website = make_business("medium", website=None, rating=3.0, reviews=0)
        website = make_business("website", website="https://site.example", rating=5, reviews=200)
        leads = [high, website, no_website, hot]

        self.assertEqual(
            [item.place_id for item in filter_businesses(leads, hot_leads_only=True)], ["hot"]
        )
        self.assertEqual(
            [item.place_id for item in filter_businesses(leads, high_score_only=True)], ["high"]
        )
        self.assertTrue(all(item.website is None for item in filter_businesses(leads, no_website_only=True)))
        self.assertEqual(
            [item.place_id for item in filter_businesses(leads, sort_by="Most Reviews")],
            ["website", "hot", "high", "medium"],
        )
        self.assertEqual(
            [item.place_id for item in filter_businesses(leads, sort_by="Highest Opportunity Score")][:2],
            ["hot", "high"],
        )
        self.assertEqual(
            filter_businesses(leads, sort_by="Highest Rating")[0].place_id, "website"
        )
        self.assertEqual(
            [item.place_id for item in filter_businesses(leads, sort_by="No Website First")][0],
            "hot",
        )

    def test_discovery_filter_call_accepts_all_current_ui_options(self) -> None:
        result = filter_businesses(
            self.businesses,
            website_filter="Show All",
            high_opportunity_only=False,
            hot_leads_only=False,
            high_score_only=False,
            no_website_only=False,
            best_leads_only=False,
            minimum_rating=0.0,
            minimum_reviews=0,
            sort_by="Highest Opportunity Score",
        )

        self.assertEqual(len(result), 2)

    def test_best_leads_filter_and_kpi(self) -> None:
        best = Business(
            name="Qualified",
            address="Hyderabad",
            rating=4.0,
            reviews_count=100,
            website=None,
            phone="555-0100",
            maps_url=None,
            place_id="qualified",
        )
        not_best = Business(
            name="No phone",
            address="Hyderabad",
            rating=4.8,
            reviews_count=250,
            website=None,
            phone=None,
            maps_url=None,
            place_id="not-qualified",
        )
        result_set = [best, not_best]

        self.assertEqual(
            [business.place_id for business in filter_businesses(result_set, best_leads_only=True)],
            ["qualified"],
        )
        self.assertEqual(summary_metrics(result_set)["best_leads"], 1)

    def test_competitor_snapshot_excludes_selected_business(self) -> None:
        selected = self.businesses[0]
        snapshot = competitor_snapshot(selected, self.businesses)

        self.assertEqual(snapshot["total_competitors"], 2)
        self.assertEqual(snapshot["with_website"], 1)
        self.assertEqual(snapshot["without_website"], 1)
        self.assertEqual(snapshot["website_penetration"], 50.0)
        self.assertEqual(snapshot["market_opportunity"], 50.0)

    def test_competitor_snapshot_marks_empty_market_rates_unavailable(self) -> None:
        snapshot = competitor_snapshot(self.businesses[0], [self.businesses[0]])

        self.assertEqual(snapshot["total_competitors"], 0)
        self.assertIsNone(snapshot["website_penetration"])
        self.assertIsNone(snapshot["market_opportunity"])

    def test_supported_niche_maps_to_nearby_type(self) -> None:
        self.assertEqual(supported_place_types(" Furniture   Stores "), ("furniture_store",))
        self.assertEqual(supported_place_types("Boutiques"), ("clothing_store",))
        self.assertEqual(supported_place_types("gyms"), ("gym",))
        self.assertEqual(supported_place_types("real estate"), ("real_estate_agency",))
        self.assertEqual(supported_place_types("real estate agencies"), ("real_estate_agency",))
        self.assertIsNone(supported_place_types("consultancies"))
        self.assertIsNone(supported_place_types("Independent repair specialists"))


if __name__ == "__main__":
    unittest.main()