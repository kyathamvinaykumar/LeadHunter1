"""Streamlit interface for local business discovery and prospect shortlisting."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from html import escape
from urllib.parse import urlsplit, urlunsplit

import pandas as pd
import streamlit as st

from app.config import ConfigurationError, load_settings
from app.crm import (
    PROSPECT_STATUSES,
    Prospect,
    crm_export_csv,
    crm_summary,
    filter_prospects,
    normalize_prospects,
    update_prospect,
)
from app.dashboard import (
    businesses_csv,
    businesses_json,
    competitor_snapshot,
    filter_businesses,
    summary_metrics,
)
from app.models import Business
from app.services.geocoding_service import GeocodingError, GeocodingService
from app.services.places_service import MAX_RESULTS, PlacesAPIError, PlacesService
from app.services.screenshot_provider import (
    ScreenshotError,
    ScreenshotMode,
    ThumIoScreenshotProvider,
)
from app.services.website_audit import (
    WebsiteAuditError,
    WebsiteAuditResult,
    WebsiteAuditor,
)
from app.utils.place_types import supported_place_types
from app.utils.validators import validate_search_input


st.set_page_config(
    page_title="LeadHunter | Local Prospecting",
    page_icon="L",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root { color-scheme: dark; }
        .stApp { background: #0d1214; }
        [data-testid="stSidebar"] {
            background: #11191b;
            border-right: 1px solid #253235;
            width: 245px !important;
            min-width: 238px;
            max-width: 245px !important;
        }
        [data-testid="stSidebar"] > div { padding-top: 1.2rem; }
        .block-container { padding: 1.7rem 2.2rem 3rem; max-width: 1540px; }
        .brand-lockup { display: flex; align-items: center; gap: 10px; margin: 0 0 1.7rem; }
        .brand-mark {
            display: grid; place-items: center; width: 34px; height: 34px; border-radius: 9px;
            background: #00e5a8; color: #071713; font-size: 18px; font-weight: 900;
            box-shadow: 0 5px 18px #00e5a833;
        }
        .brand-name { color: #f2f7f5; font-size: 15px; font-weight: 750; line-height: 1.05; }
        .brand-caption { color: #71817f; font-size: 10px; margin-top: 4px; text-transform: uppercase; }
        .eyebrow { color: #00e5a8; font-size: .72rem; font-weight: 750; text-transform: uppercase; letter-spacing: .1em; }
        .page-title { color: #f2f7f5; font-size: 2.2rem; line-height: 1.15; font-weight: 750; margin: .2rem 0 .3rem; }
        .page-subtitle { color: #9aa9a6; font-size: .96rem; margin: 0 0 1.25rem; }
        .section-heading { color: #edf3f1; font-size: 1.15rem; font-weight: 700; margin: .3rem 0 .9rem; }
        div[data-testid="stForm"] { background: #151e20; border: 1px solid #293638; border-radius: 12px; padding: .55rem .85rem .2rem; box-shadow: 0 12px 30px #00000020; }
        .lead-metric {
            position: relative; overflow: hidden; min-height: 115px; padding: 18px 20px;
            background: linear-gradient(145deg, #192326, #141b1d); border: 1px solid #2a383a;
            border-radius: 12px; box-shadow: 0 8px 22px #00000024;
        }
        .lead-metric::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--metric-accent); }
        .metric-label { color: #9aaba8; font-size: .77rem; font-weight: 600; }
        .metric-value { color: #f4f8f7; font-size: 1.85rem; line-height: 1.2; font-weight: 750; margin-top: 8px; }
        .metric-foot { color: #72827f; font-size: .72rem; margin-top: 5px; }
        .status-good { color: #00e5a8; font-weight: 700; }
        .status-missing { color: #ff6b6b; font-weight: 750; }
        .lead-name { color: #eff5f3; font-size: 1.03rem; line-height: 1.3; font-weight: 700; margin: 0; }
        .lead-meta { color: #99aaa7; font-size: .83rem; line-height: 1.55; }
        .lead-address { color: #aab8b5; font-size: .84rem; line-height: 1.45; overflow-wrap: anywhere; }
        .opportunity-card { border-left: 3px solid #ff6b6b !important; }
        .score-badge { display: inline-block; padding: 4px 8px; border-radius: 5px; font-size: .68rem; font-weight: 800; white-space: nowrap; }
        .score-hot { background: #123a2d; color: #00e5a8; border: 1px solid #23684f; }
        .score-high { background: #123441; color: #00c2ff; border: 1px solid #1a6078; }
        .score-medium { background: #40301b; color: #ffb547; border: 1px solid #76511f; }
        .score-low { background: #272e30; color: #aab4b2; border: 1px solid #414b4d; }
        .lead-score-badge { display: inline-block; padding: 5px 9px; border-radius: 6px; font-size: .78rem; font-weight: 850; white-space: nowrap; }
        .lead-score-best { background: #123a2d; color: #00e5a8; border: 1px solid #23684f; }
        .lead-score-strong { background: #123441; color: #00c2ff; border: 1px solid #1a6078; }
        .lead-score-base { background: #272e30; color: #c0cbc8; border: 1px solid #414b4d; }
        .audit-pass { color: #00e5a8; font-weight: 700; }
        .audit-fail { color: #ff6b6b; font-weight: 700; }
        .audit-unknown { color: #98a7a4; font-weight: 700; }
        .detail-label { color: #8d9d9a; font-size: .75rem; text-transform: uppercase; }
        .detail-value { color: #edf3f1; font-size: .92rem; font-weight: 600; overflow-wrap: anywhere; }
        .stButton > button, .stLinkButton > a, .stDownloadButton > button {
            border-radius: 7px; font-weight: 650; transition: border-color .15s ease, transform .15s ease;
        }
        .stButton > button:hover, .stLinkButton > a:hover, .stDownloadButton > button:hover { transform: translateY(-1px); border-color: #00c2ff; }
        button[kind="primary"] { background: #00e5a8; border-color: #00e5a8; color: #071713; font-weight: 750; }
        button[kind="primary"]:hover { background: #40f0c1; border-color: #40f0c1; color: #071713; }
        [data-testid="stSegmentedControl"] button[aria-pressed="true"] { color: #00e5a8; }
        div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] { border: 1px solid #293638; border-radius: 9px; }
        .empty-state { min-height: 270px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
        .empty-icon { display: grid; place-items: center; height: 62px; width: 62px; margin-bottom: 16px; border: 1px solid #31514b; border-radius: 18px; color: #00e5a8; background: #132521; font-size: 31px; }
        .empty-title { color: #eef4f2; font-size: 1.05rem; font-weight: 700; }
        .empty-copy { color: #849491; font-size: .87rem; }
        hr { border-color: #253235; }
        @media (max-width: 900px) {
            .block-container { padding: 1rem 0 2.5rem; }
            .page-title { font-size: 1.8rem; }
            div[data-testid="stForm"] { overflow-x: auto; padding: .3rem .05rem .1rem; }
            div[data-testid="stForm"] [data-testid="stHorizontalBlock"] { min-width: 520px; gap: .4rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _header(title: str, subtitle: str) -> None:
    st.markdown('<div class="eyebrow">LEADHUNTER / LOCAL PROSPECTING</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def _initialize_state() -> None:
    st.session_state.setdefault("businesses", [])
    st.session_state.setdefault("prospects", {})
    st.session_state.setdefault("search_city", "")
    st.session_state.setdefault("search_niche", "")
    st.session_state.setdefault("minimum_rating", 0.0)
    st.session_state.setdefault("minimum_reviews", 0)
    st.session_state.setdefault("search_mode", "")
    st.session_state.setdefault("search_revision", 0)
    st.session_state.setdefault("website_audits", {})
    st.session_state.setdefault("website_screenshots", {})
    st.session_state.setdefault("selected_business_id", None)
    st.session_state.setdefault("hot_leads_only", False)
    st.session_state.setdefault("high_score_only", False)
    st.session_state.setdefault("no_website_only", False)
    st.session_state.setdefault("best_leads_only", False)
    st.session_state.setdefault("lead_sort", "Highest Opportunity Score")
    st.session_state.prospects = normalize_prospects(st.session_state.prospects)
    st.session_state.setdefault("crm_status_filter", "All Leads")
    st.session_state.setdefault("crm_no_website_only", False)
    st.session_state.setdefault("crm_hot_leads_only", False)
    st.session_state.setdefault("crm_editing_place_id", None)


def _search_form() -> None:
    st.markdown('<div class="section-heading">Find local businesses</div>', unsafe_allow_html=True)
    with st.form("business_search"):
        city_column, niche_column, radius_column, count_column, button_column = st.columns(
            [1.7, 1.8, .8, .75, .8], vertical_alignment="bottom"
        )
        city = city_column.text_input("Location", placeholder="City")
        niche = niche_column.text_input(
            "Business niche",
            placeholder="e.g. Furniture stores, boutiques, gyms, consultancies",
        )
        radius_km = radius_column.number_input("Radius km", 1, 50, 10, step=1)
        max_results = count_column.number_input("Max", 1, MAX_RESULTS, 20, step=1)
        submitted = button_column.form_submit_button(
            "Search", type="primary", width="stretch"
        )

    if not submitted:
        return
    try:
        city, niche = validate_search_input(city, niche)
        settings = load_settings()
        geocoding = GeocodingService()
        latitude, longitude = geocoding.resolve_city(city)
        places = PlacesService(settings.google_maps_api_key)
        types = supported_place_types(niche)
        if types and max_results <= 20:
            businesses = places.search_nearby(
                included_types=list(types),
                latitude=latitude,
                longitude=longitude,
                radius_km=float(radius_km),
                max_results=max_results,
            )
            search_mode = "Nearby Search: Google enforces the selected radius; this search returns up to 20 results."
        else:
            businesses = places.search_businesses_biased(
                city=city,
                niche=niche,
                latitude=latitude,
                longitude=longitude,
                radius_km=float(radius_km),
                max_results=max_results,
            )
            search_mode = "Text Search: the selected radius is a location bias, not a strict boundary. Results may be outside it."
            if types:
                search_mode += " Text Search is used because the requested limit is above Nearby Search's 20-result cap."

        st.session_state.businesses = businesses
        st.session_state.search_city = city
        st.session_state.search_niche = niche
        st.session_state.search_mode = search_mode
        st.session_state.search_revision += 1
        st.success(f"Found {len(businesses)} businesses.")
    except (ValueError, ConfigurationError, GeocodingError, PlacesAPIError) as error:
        st.error(str(error))


def _sidebar() -> str:
    st.sidebar.markdown(
        '<div class="brand-lockup"><div class="brand-mark">L</div><div>'
        '<div class="brand-name">LeadHunter</div><div class="brand-caption">Agency workspace</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    page = st.sidebar.radio(
        "Workspace", ["Discovery", "Prospects"], label_visibility="collapsed"
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        f'<div class="metric-label">SHORTLISTED</div>'
        f'<div style="font-size:1.5rem;font-weight:750;color:#00e5a8;margin:.2rem 0 1.2rem">'
        f'{len(st.session_state.prospects)}</div>',
        unsafe_allow_html=True,
    )
    if page == "Discovery":
        st.sidebar.markdown("#### Filters")
        st.sidebar.selectbox(
            "Website status",
            ["Show All", "No Website Only", "Has Website Only"],
            key="website_filter",
        )
        st.sidebar.checkbox("Show Only High Opportunity Leads", key="high_opportunity_filter")
        st.sidebar.checkbox("Show HOT LEADS only", key="hot_leads_only")
        st.sidebar.checkbox("Show HIGH OPPORTUNITY only", key="high_score_only")
        st.sidebar.checkbox("Show No Website only", key="no_website_only")
        st.sidebar.checkbox("Best Leads", key="best_leads_only")
        st.sidebar.selectbox(
            "Sort by",
            [
                "Highest Opportunity Score",
                "Highest Rating",
                "Most Reviews",
                "No Website First",
            ],
            key="lead_sort",
        )
        st.sidebar.slider("Rating >=", 0.0, 5.0, step=0.5, key="minimum_rating")
        st.sidebar.number_input(
            "Reviews >=", min_value=0, max_value=100000, step=10, key="minimum_reviews"
        )
    st.sidebar.markdown("---")
    st.sidebar.caption("Geocoding by [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)")
    return page


def _show_metrics(businesses: list[Business]) -> None:
    metrics = summary_metrics(businesses)
    columns = st.columns(5)
    cards = [
        ("Total Businesses", str(metrics["total"]), "Current search results", "#00E5A8"),
        ("Best Leads Count", str(metrics["best_leads"]), "Ready to contact", "#00E5A8"),
        ("No Website Leads", str(metrics["without_website"]), "High opportunity", "#FF6B6B"),
        ("Has Website Leads", str(metrics["with_website"]), "Website found", "#00C2FF"),
        ("Average Rating", f'{metrics["average_rating"]:.1f}', "Across rated businesses", "#FFB547"),
    ]
    for column, (label, value, foot, accent) in zip(columns, cards, strict=True):
        column.markdown(
            f'<div class="lead-metric" style="--metric-accent:{accent}">'
            f'<div class="metric-label">{label}</div><div class="metric-value">{value}</div>'
            f'<div class="metric-foot">{foot}</div></div>',
            unsafe_allow_html=True,
        )


def _selected_businesses() -> list[Business]:
    return [prospect.to_business() for prospect in st.session_state.prospects.values()]


def _filename_suffix() -> str:
    city = re.sub(r"[^a-z0-9]+", "_", st.session_state.search_city.casefold()).strip("_") or "search"
    niche = re.sub(r"[^a-z0-9]+", "_", st.session_state.search_niche.casefold()).strip("_") or "leads"
    return f"{city}_{niche}"


def _audit_cache_key(website: str) -> str:
    parsed = urlsplit(website.strip())
    normalized = parsed._replace(
        scheme=parsed.scheme.casefold(),
        netloc=parsed.netloc.casefold(),
        path=parsed.path.rstrip("/"),
    )
    return urlunsplit(normalized)


def _audit_result_for(business: Business) -> WebsiteAuditResult | None:
    if not business.website:
        return None
    return st.session_state.website_audits.get(_audit_cache_key(business.website))


def _audits_for(businesses: list[Business]) -> dict[str, dict[str, object]]:
    audit_fields: dict[str, dict[str, object]] = {}
    for business in businesses:
        result = _audit_result_for(business)
        if result is not None:
            audit_fields[business.place_id] = result.to_export_dict()
    return audit_fields


def _download_buttons(results: list[Business]) -> None:
    columns = st.columns(3)
    suffix = _filename_suffix()
    audit_fields = _audits_for(results)
    columns[0].download_button(
        "Export Results CSV",
        data=businesses_csv(results, audit_fields),
        file_name=f"{suffix}_results.csv",
        mime="text/csv",
        width="stretch",
    )
    columns[1].download_button(
        "Export Results JSON",
        data=businesses_json(results, audit_fields),
        file_name=f"{suffix}_results.json",
        mime="application/json",
        width="stretch",
    )
    columns[2].download_button(
        "Export Prospects CSV",
        data=businesses_csv(_selected_businesses(), _audits_for(_selected_businesses())),
        file_name=f"{suffix}_prospects.csv",
        mime="text/csv",
        width="stretch",
    )


def _render_list_view(businesses: list[Business]) -> None:
    if not businesses:
        st.info("No businesses match the current filters.")
        return

    for business in businesses:
        _render_business_card(business, allow_shortlist=True)


def _score_badge(business: Business) -> str:
    css_class = (
        "lead-score-best" if business.is_best_lead
        else "lead-score-strong" if business.lead_score >= 80
        else "lead-score-base"
    )
    return (
        f'<span class="lead-score-badge {css_class}">'
        f'LEAD SCORE {business.lead_score}/100</span>'
    )


def _render_business_card(
    business: Business,
    *,
    allow_shortlist: bool = False,
    allow_remove: bool = False,
) -> None:
    has_website = bool(business.website)
    website_color = "#00E5A8" if has_website else "#FF6B6B"
    website_status = "HAS WEBSITE" if has_website else "NO WEBSITE · HIGH OPPORTUNITY"
    audit_result = _audit_result_for(business)
    with st.container(border=True):
        title_column, rating_column, score_column, status_column = st.columns(
            [4.2, .8, 1.5, 2.1], vertical_alignment="center"
        )
        title_column.markdown(
            f'<div class="lead-name" style="border-left:3px solid {website_color};padding-left:11px">'
            f'{escape(business.name)}</div>',
            unsafe_allow_html=True,
        )
        title_column.markdown(
            f'<div class="lead-meta">{business.phone or "Phone unavailable"} '
            f'&nbsp;·&nbsp; {business.reviews_count:,} reviews</div>',
            unsafe_allow_html=True,
        )
        rating_column.markdown(
            f'<div style="color:#FFB547;font-size:1.05rem;font-weight:750">'
            f'★ {business.rating:.1f}</div>' if business.rating is not None
            else '<div class="lead-meta">Not rated</div>',
            unsafe_allow_html=True,
        )
        score_column.markdown(_score_badge(business), unsafe_allow_html=True)
        status_column.markdown(
            f'<div style="color:{website_color};font-size:.68rem;font-weight:800;'
            f'letter-spacing:.03em;text-align:right">{website_status}</div>',
            unsafe_allow_html=True,
        )
        details_column, links_column = st.columns([3, 2], vertical_alignment="center")
        details_column.markdown(
            f'<div class="lead-address">{escape(business.address)}</div>',
            unsafe_allow_html=True,
        )
        if business.website:
            details_column.markdown(f"[Website]({business.website})")
        actions = links_column.columns(3)
        phone_url = f"tel:{re.sub(r'[^+0-9]', '', business.phone or '')}"
        if business.phone:
            actions[0].link_button("Call", phone_url, width="stretch")
        else:
            actions[0].button("Call", disabled=True, width="stretch", key=f"call_{business.place_id}")
        if business.maps_url:
            actions[1].link_button("Maps", business.maps_url, width="stretch")
        else:
            actions[1].button("Maps", disabled=True, width="stretch", key=f"maps_{business.place_id}")
        if allow_remove:
            actions[2].button(
                "Remove", width="stretch", key=f"prospect_remove_{business.place_id}",
                on_click=_remove_prospect, args=(business.place_id,),
            )
        elif allow_shortlist:
            prospects: dict[str, Business] = st.session_state.prospects
            already_added = business.place_id in prospects
            if actions[2].button(
                "Added" if already_added else "Add To Prospects",
                type="secondary" if already_added else "primary",
                disabled=already_added,
                width="stretch",
                key=f"prospect_add_{business.place_id}",
            ):
                prospects[business.place_id] = Prospect.from_business(business)
                st.session_state.prospects = prospects
                st.rerun()

        action_columns = st.columns([1.5, 1.5, 4.0])
        if action_columns[0].button("View Details", key=f"details_{business.place_id}", width="stretch"):
            st.session_state.selected_business_id = business.place_id
        if audit_result:
            action_columns[1].markdown(
                '<span class="score-badge score-low">'
                f'AUDIT {audit_result.score}/10</span>',
                unsafe_allow_html=True,
            )


def _render_audit_panel(result: WebsiteAuditResult) -> None:
    st.markdown("#### Website audit")
    audit_summary_columns = st.columns(2)
    audit_summary_columns[0].metric(
        "Website Score",
        f"{result.score}/10" if result.score is not None else "Unknown",
    )
    audit_summary_columns[1].metric("Website Quality", result.quality_status)
    checks = st.columns(3)
    for index, (label, passed) in enumerate(result.checks().items()):
        css_class = "audit-pass" if passed is True else "audit-fail" if passed is False else "audit-unknown"
        checks[index % len(checks)].markdown(
            f'<div class="detail-label">{label}</div>'
            f'<div class="{css_class}">'
            f'{"PASS" if passed is True else "FAIL" if passed is False else "UNKNOWN"}</div>',
            unsafe_allow_html=True,
        )
    reachability = "Reachable" if result.reachable else "Unreachable"
    https_status = "HTTPS" if result.https is True else "Not HTTPS" if result.https is False else "Unknown"
    response_time = f"{result.response_time_ms:.0f} ms" if result.response_time_ms is not None else "Unknown"
    title = result.page_title or "Unknown"
    builder = result.website_builder or "Unknown"
    facts = st.columns(4)
    facts[0].markdown(f'**Reachability**  \n{reachability}')
    facts[1].markdown(f'**HTTPS Status**  \n{https_status}')
    facts[2].markdown(f'**Response Time**  \n{response_time}')
    facts[3].markdown(f'**Website Builder**  \n{builder}')
    st.markdown(f"**Page Title:** {escape(title)}")
    st.markdown(f"**Meta Description:** {escape(result.meta_description_text or 'Unknown')}")
    if result.social_links:
        st.caption("Social links detected: " + ", ".join(result.social_links))
    st.caption(result.summary)


def _close_details_dialog() -> None:
    st.session_state.selected_business_id = None


@st.dialog("Lead Details", width="large", on_dismiss=_close_details_dialog)
def _lead_details_dialog(place_id: str) -> None:
    businesses = [
        *st.session_state.businesses,
        *(prospect.to_business() for prospect in st.session_state.prospects.values()),
    ]
    business = next((item for item in businesses if item.place_id == place_id), None)
    if business is None:
        return

    st.markdown(f"### {escape(business.name)}")
    website_status = "No Website" if not business.website else "Has Website"
    audit_result = _audit_result_for(business)
    website_quality = (
        "No Website" if not business.website
        else audit_result.quality_status if audit_result
        else "Not audited"
    )
    summary_cards = st.columns(4)
    summary_data = [
        ("Website Status", website_status, "#FF6B6B" if not business.website else "#00E5A8"),
        ("Website Quality", website_quality, "#00C2FF"),
        ("Lead Score", f"{business.lead_score}/100", "#00E5A8"),
        ("Opportunity Score", f"{business.opportunity_score}/100", "#FFB547"),
    ]
    for column, (label, value, accent) in zip(summary_cards, summary_data, strict=True):
        column.markdown(
            f'<div class="lead-metric" style="--metric-accent:{accent};min-height:88px;padding:12px">'
            f'<div class="metric-label">{label}</div><div class="metric-value" '
            f'style="font-size:1.25rem">{escape(value)}</div></div>',
            unsafe_allow_html=True,
        )

    detail_columns = st.columns(4)
    details = [
        ("Rating", f"{business.rating:.1f}" if business.rating is not None else "Unknown"),
        ("Reviews", f"{business.reviews_count:,}"),
        ("Phone", business.phone or "Unknown"),
        ("Website", business.website or "No Website"),
        ("Address", business.address or "Unknown"),
    ]
    for index, (label, value) in enumerate(details):
        detail_columns[index % len(detail_columns)].markdown(
            f'<div class="detail-label">{escape(label)}</div>'
            f'<div class="detail-value">{escape(value)}</div>',
            unsafe_allow_html=True,
        )
    if business.website:
        reasons = business.opportunity_reasons
        st.markdown("**Opportunity Reasons**")
        if reasons:
            st.markdown("  \n".join(f"✓ {escape(reason)}" for reason in reasons))
        else:
            st.caption("No score criteria met yet.")
    else:
        st.markdown("**Opportunity Reasons**")
        st.markdown("✓ No Website")

    st.markdown("#### Website Audit")
    if not business.website:
        st.info("No Website: audit and screenshots are unavailable.")
    else:
        initial_https = "HTTPS URL" if urlsplit(business.website).scheme.casefold() == "https" else "Not HTTPS"
        signal_values = {
            "HTTPS Status": (
                ("HTTPS" if audit_result.https else "Not HTTPS")
                if audit_result and audit_result.https is not None else initial_https
            ),
            "Reachability": (
                "Reachable" if audit_result.reachable else "Unreachable"
            ) if audit_result else "Not checked",
            "Response Time": (
                f"{audit_result.response_time_ms:.0f} ms"
                if audit_result and audit_result.response_time_ms is not None else "Not measured"
            ),
            "Page Title": audit_result.page_title if audit_result and audit_result.page_title else "Unknown",
            "Meta Description": (
                audit_result.meta_description_text
                if audit_result and audit_result.meta_description_text else "Unknown"
            ),
            "Website Builder": audit_result.website_builder if audit_result else "Unknown",
        }
        signal_columns = st.columns(3)
        for index, (label, value) in enumerate(signal_values.items()):
            signal_columns[index % len(signal_columns)].markdown(
                f'<div class="detail-label">{escape(label)}</div>'
                f'<div class="detail-value">{escape(value)}</div>',
                unsafe_allow_html=True,
            )
        if audit_result is None:
            st.info("Website audit not performed yet.")
            st.caption("Run an audit to inspect reachability, response time, metadata, and builder signals.")
        else:
            _render_audit_panel(audit_result)

        audit_action = st.columns([1.3, 2.7])
        audit_label = "Run Website Audit" if audit_result is None else "Re-run Website Audit"
        if audit_action[0].button(audit_label, key=f"dialog_audit_{business.place_id}", type="primary"):
            with st.spinner("Checking this website..."):
                result = WebsiteAuditor().audit(business.website)
                st.session_state.website_audits[_audit_cache_key(business.website)] = result
            st.rerun()

        st.markdown("#### Screenshot Preview")
        preview_key = _audit_cache_key(business.website)
        previews = st.session_state.website_screenshots.setdefault(preview_key, {})
        desktop_column, mobile_column = st.columns(2)
        modes: tuple[tuple[object, ScreenshotMode, str], ...] = (
            (desktop_column, "desktop", "Desktop Screenshot"),
            (mobile_column, "mobile", "Mobile Screenshot"),
        )
        for column, mode, label in modes:
            if mode not in previews and column.button(
                f"Load {label}", key=f"screenshot_{mode}_{business.place_id}", width="stretch"
            ):
                with st.spinner(f"Capturing {label.lower()}..."):
                    try:
                        image_data = ThumIoScreenshotProvider().capture(business.website, mode)
                    except (ScreenshotError, ValueError) as error:
                        st.error(str(error))
                    else:
                        previews[mode] = image_data
                        st.rerun()
            if mode in previews:
                column.image(previews[mode], caption=label, width="stretch")

    st.markdown("#### Nearby Businesses in This Search")
    snapshot = competitor_snapshot(business, st.session_state.businesses)
    snapshot_cards = [
        ("Total Competitors", str(snapshot["total_competitors"]), "#00C2FF"),
        ("With Websites", str(snapshot["with_website"]), "#00E5A8"),
        ("Without Websites", str(snapshot["without_website"]), "#FF6B6B"),
        (
            "Website Penetration",
            f'{snapshot["website_penetration"]:.1f}%'
            if snapshot["website_penetration"] is not None else "N/A",
            "#FFB547",
        ),
        (
            "Market Opportunity",
            f'{snapshot["market_opportunity"]:.1f}%'
            if snapshot["market_opportunity"] is not None else "N/A",
            "#00E5A8",
        ),
    ]
    metric_columns = st.columns(5)
    for column, (label, value, accent) in zip(metric_columns, snapshot_cards, strict=True):
        column.markdown(
            f'<div class="lead-metric" style="--metric-accent:{accent};min-height:82px;padding:10px">'
            f'<div class="metric-label">{label}</div><div class="metric-value" '
            f'style="font-size:1.25rem">{value}</div></div>',
            unsafe_allow_html=True,
        )


def _render_details_panel() -> None:
    place_id = st.session_state.selected_business_id
    if place_id:
        _lead_details_dialog(place_id)


def _render_map_view(businesses: list[Business]) -> None:
    mapped = [business for business in businesses if business.latitude is not None and business.longitude is not None]
    if not mapped:
        st.info("No map coordinates are available for these results.")
        return

    import pydeck as pdk

    rows = [
        {
            "place_id": business.place_id,
            "name": business.name,
            "rating": business.rating if business.rating is not None else "Not rated",
            "website_status": "Has Website" if business.website else "No Website",
            "phone": business.phone or "Not available",
            "latitude": business.latitude,
            "longitude": business.longitude,
            "color": [85, 214, 190, 210] if business.website else [255, 112, 103, 230],
        }
        for business in mapped
    ]
    frame = pd.DataFrame(rows)
    deck = pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(
            latitude=float(frame["latitude"].mean()),
            longitude=float(frame["longitude"].mean()),
            zoom=11,
            pitch=0,
        ),
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                data=frame,
                id="business-markers",
                get_position="[longitude, latitude]",
                get_fill_color="color",
                get_line_color=[232, 239, 237, 230],
                get_radius=115,
                radius_min_pixels=6,
                radius_max_pixels=16,
                line_width_min_pixels=1,
                pickable=True,
                auto_highlight=True,
            )
        ],
        tooltip={
            "html": "<b>{name}</b><br/>Rating: {rating}<br/>{website_status}<br/>{phone}",
            "style": {"backgroundColor": "#182022", "color": "#eef4f2"},
        },
    )
    selection = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object", key="business_map")
    selected_objects = selection.get("selection", {}).get("objects", {}).get("business-markers", [])
    if selected_objects:
        selected = selected_objects[0]
        status = "Has Website" if selected["website_status"] == "Has Website" else "No Website"
        status_class = "status-good" if status == "Has Website" else "status-missing"
        st.markdown(f"### {selected['name']}")
        st.write(f"Rating: {selected['rating']}")
        st.markdown(f'Website Status: <span class="{status_class}">{status}</span>', unsafe_allow_html=True)
        st.write(f"Phone Number: {selected['phone']}")


def _discovery_page() -> None:
    _header("Business discovery", "Find local businesses, spot website gaps, and shortlist prospects.")
    _search_form()
    businesses: list[Business] = st.session_state.businesses
    if not businesses:
        if st.session_state.search_revision:
            st.markdown(
                '<div class="empty-state"><div class="empty-icon">⌕</div>'
                '<div class="empty-title">No businesses found for this search.</div>'
                '<div class="empty-copy">Try another niche or expand the search radius.</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="empty-state"><div class="empty-icon">⌕</div>'
                '<div class="empty-title">Search a niche and location to discover local businesses.</div>'
                '<div class="empty-copy">Your results and shortlist will appear here.</div></div>',
                unsafe_allow_html=True,
            )
        return

    if st.session_state.search_mode:
        st.info(st.session_state.search_mode)
    _show_metrics(businesses)

    st.markdown('<div class="section-heading">Lead results</div>', unsafe_allow_html=True)
    view = st.segmented_control(
        "Results view",
        ["List View", "Map View"],
        default="List View",
        key="results_view",
    ) or "List View"

    filtered = filter_businesses(
        businesses,
        website_filter=st.session_state.website_filter,
        high_opportunity_only=st.session_state.high_opportunity_filter,
        hot_leads_only=st.session_state.hot_leads_only,
        high_score_only=st.session_state.high_score_only,
        no_website_only=st.session_state.no_website_only,
        best_leads_only=st.session_state.best_leads_only,
        minimum_rating=st.session_state.minimum_rating,
        minimum_reviews=st.session_state.minimum_reviews,
        sort_by=st.session_state.lead_sort,
    )
    st.caption(
        f"Showing {len(filtered)} of {len(businesses)} results · "
        f"Rating ≥ {st.session_state.minimum_rating:g} · "
        f"Reviews ≥ {st.session_state.minimum_reviews}"
    )
    _download_buttons(filtered)
    if view == "Map View":
        _render_map_view(filtered)
    else:
        _render_list_view(filtered)
    _render_details_panel()


def _crm_widget_key(field: str, place_id: str) -> str:
    return f"crm_{field}_{place_id}"


def _save_crm_widget(place_id: str, field: str) -> None:
    prospect = st.session_state.prospects.get(place_id)
    if prospect is None:
        return
    key = _crm_widget_key(field, place_id)
    try:
        st.session_state.prospects[place_id] = update_prospect(
            prospect, **{field: st.session_state[key]}
        )
    except ValueError as error:
        st.session_state[f"crm_error_{place_id}"] = str(error)


def _render_crm_card(prospect: Prospect) -> None:
    place_id = prospect.place_id
    status_key = _crm_widget_key("status", place_id)
    st.session_state.setdefault(status_key, prospect.status)
    is_overdue = (
        prospect.status == "Follow Up"
        and prospect.followup_date is not None
        and prospect.followup_date < date.today()
    )
    with st.container(border=True):
        name_column, score_column, status_column = st.columns([4.5, 1.5, 2], vertical_alignment="center")
        name_column.markdown(
            f'<div class="lead-name" style="border-left:3px solid '
            f'{"#FF6B6B" if not prospect.website else "#00E5A8"};padding-left:11px">'
            f'{escape(prospect.business_name)}</div>',
            unsafe_allow_html=True,
        )
        name_column.markdown(
            f'<div class="lead-meta">{escape(prospect.phone or "Phone unavailable")} '
            f'&nbsp;·&nbsp; {prospect.reviews:,} reviews · '
            f'{"Has Website" if prospect.website else "No Website"}</div>',
            unsafe_allow_html=True,
        )
        score_column.markdown(_score_badge(prospect.to_business()), unsafe_allow_html=True)
        status_column.selectbox(
            "Status",
            PROSPECT_STATUSES,
            key=status_key,
            on_change=_save_crm_widget,
            args=(place_id, "status"),
            label_visibility="collapsed",
        )

        info_columns = st.columns([1, 1, 2, 2], vertical_alignment="center")
        info_columns[0].markdown(
            f'<div class="lead-meta">Rating<br><b>{prospect.rating:.1f}</b></div>'
            if prospect.rating is not None
            else '<div class="lead-meta">Rating<br><b>Unknown</b></div>',
            unsafe_allow_html=True,
        )
        info_columns[1].markdown(
            f'<div class="lead-meta">Lead Score<br><b>{prospect.lead_score}/100</b></div>',
            unsafe_allow_html=True,
        )
        followup_text = prospect.followup_date.strftime("%d %b %Y") if prospect.followup_date else "Not set"
        info_columns[2].markdown(
            f'<div class="lead-meta">Next Follow-Up<br><b>{followup_text}</b></div>',
            unsafe_allow_html=True,
        )
        if is_overdue:
            info_columns[3].markdown(
                '<span class="score-badge score-hot">OVERDUE FOLLOW-UP</span>',
                unsafe_allow_html=True,
            )
        elif prospect.website:
            info_columns[3].markdown(f"[Open Website]({prospect.website})")
        else:
            info_columns[3].markdown('<span class="status-missing">NO WEBSITE</span>', unsafe_allow_html=True)

        action_columns = st.columns([1.2, 1.2, 1.2, 4.4])
        if action_columns[0].button("View Details", key=f"crm_details_{place_id}", width="stretch"):
            st.session_state.selected_business_id = place_id
        if action_columns[1].button("Edit Prospect", key=f"crm_edit_{place_id}", width="stretch"):
            current = st.session_state.crm_editing_place_id
            st.session_state.crm_editing_place_id = None if current == place_id else place_id
        if action_columns[2].button("Remove Prospect", key=f"crm_remove_{place_id}", width="stretch"):
            st.session_state.prospects.pop(place_id, None)
            st.session_state.crm_editing_place_id = None
            st.rerun()

        with st.expander("Internal Notes", expanded=False):
            notes_key = _crm_widget_key("notes", place_id)
            st.session_state.setdefault(notes_key, prospect.notes)
            st.text_area(
                "Notes",
                key=notes_key,
                placeholder='e.g. "Owner answered call"',
                label_visibility="collapsed",
                on_change=_save_crm_widget,
                args=(place_id, "notes"),
            )

        if st.session_state.crm_editing_place_id == place_id:
            contacted_key = _crm_widget_key("contacted_date", place_id)
            followup_key = _crm_widget_key("followup_date", place_id)
            st.session_state.setdefault(contacted_key, prospect.contacted_date or date.today())
            st.session_state.setdefault(followup_key, prospect.followup_date or date.today())
            dates = st.columns(2)
            dates[0].date_input(
                "Contacted Date",
                key=contacted_key,
                on_change=_save_crm_widget,
                args=(place_id, "contacted_date"),
            )
            dates[1].date_input(
                "Follow-Up Date",
                key=followup_key,
                on_change=_save_crm_widget,
                args=(place_id, "followup_date"),
            )
        if error := st.session_state.pop(f"crm_error_{place_id}", None):
            st.error(error)


def _render_prospects_page() -> None:
    prospects: dict[str, Prospect] = st.session_state.prospects
    prospect_list = list(prospects.values())
    summary = crm_summary(prospect_list)
    _header("Prospect CRM", "Track outreach, next steps, and closed opportunities.")

    metrics = st.columns(5)
    metric_data = [
        ("Total Prospects", summary["total"], "#00C2FF"),
        ("Contacted", summary["contacted"], "#00E5A8"),
        ("Interested", summary["interested"], "#FFB547"),
        ("Follow Ups Due", summary["followups_due"], "#FF6B6B"),
        ("Closed Won", summary["closed_won"], "#00E5A8"),
    ]
    for column, (label, value, accent) in zip(metrics, metric_data, strict=True):
        column.markdown(
            f'<div class="lead-metric" style="--metric-accent:{accent};min-height:90px;padding:12px">'
            f'<div class="metric-label">{label}</div><div class="metric-value" '
            f'style="font-size:1.5rem">{value}</div></div>',
            unsafe_allow_html=True,
        )

    filter_columns = st.columns([1.4, 1.1, 1.1, 3.4], vertical_alignment="bottom")
    filter_columns[0].selectbox(
        "Lead status", ["All Leads", *PROSPECT_STATUSES], key="crm_status_filter"
    )
    filter_columns[1].checkbox("Only No Website Leads", key="crm_no_website_only")
    filter_columns[2].checkbox("Only Hot Leads", key="crm_hot_leads_only")
    if prospect_list:
        filter_columns[3].download_button(
            "Export CRM CSV",
            data=crm_export_csv(prospect_list),
            file_name=f"{_filename_suffix()}_crm.csv",
            mime="text/csv",
            width="stretch",
        )

    st.markdown('<div class="section-heading">Prospect list</div>', unsafe_allow_html=True)
    visible = filter_prospects(
        prospect_list,
        status=st.session_state.crm_status_filter,
        no_website_only=st.session_state.crm_no_website_only,
        hot_leads_only=st.session_state.crm_hot_leads_only,
    )
    st.caption(f"Showing {len(visible)} of {len(prospect_list)} prospects")
    if not visible:
        message = "No prospects match these filters." if prospect_list else "Add leads from Discovery to start tracking outreach."
        st.markdown(
            f'<div class="empty-state"><div class="empty-icon">＋</div>'
            f'<div class="empty-title">{escape(message)}</div></div>',
            unsafe_allow_html=True,
        )
        return

    for prospect in visible:
        _render_crm_card(prospect)
    _render_details_panel()


def _remove_prospect(place_id: str) -> None:
    st.session_state.prospects.pop(place_id, None)


def main() -> None:
    _inject_styles()
    _initialize_state()
    page = _sidebar()
    if page == "Prospects":
        _render_prospects_page()
    else:
        _discovery_page()


if __name__ == "__main__":
    main()