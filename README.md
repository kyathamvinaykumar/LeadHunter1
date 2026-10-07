# LeadHunter

LeadHunter discovers local businesses with Google Places API (New), provides a Streamlit prospecting dashboard, and exports results to CSV and JSON.

## Requirements

- Python 3.12 or newer
- A Google Maps Platform API key with Places API (New) enabled and billing configured

The selected response fields include ratings, website URLs, and phone numbers. Google may bill these under the Text Search Enterprise SKU; check current [Places API pricing](https://developers.google.com/maps/billing-and-pricing/sku-details) and configure quotas for your project.

Dashboard city geocoding uses OpenStreetMap Nominatim and does not require a Google Geocoding API key or billing. Coordinates are cached locally at `data/cache/nominatim_geocoding.json`. Nominatim requests identify this app with `LeadHunter/0.1`; set `NOMINATIM_USER_AGENT` to include your organization and contact details before running a public deployment. The service enforces Nominatim's one-request-per-second usage limit. OpenStreetMap data attribution is shown in the dashboard and is also available at [OpenStreetMap Copyright](https://www.openstreetmap.org/copyright).

## Setup

1. Install dependencies with `python -m pip install -r requirements.txt`.
2. Add your key to `.env` as `GOOGLE_MAPS_API_KEY=your_key`.
3. Run a search:

```powershell
python main.py --city Hyderabad --niche "Furniture Stores"
```

Omit either option to be prompted in the terminal. Results are limited to 60 businesses by Google; use `--max-results` to request fewer.

Exports are written to `data/exports/` with a timestamped filename. Run the offline service tests with `python -m unittest discover -s tests -v`.

## Dashboard

Install dependencies with `python -m pip install -r requirements.txt`, then launch the dashboard:

```powershell
streamlit run app.py
```

The dashboard uses Google Nearby Search (New) for supported place types when the requested result limit is at most 20. Common mapped niches include boutiques, gyms, and real estate agencies. Other searches, including consultancies, use paginated Text Search (New) with a circular location bias; Google may return results outside a bias radius. Text Search supports up to 60 results. The dashboard does not perform local distance filtering. Map rendering is built only when Map View is selected.

Dashboard exports are generated in memory and downloaded from the interface. The existing CLI and its timestamped file exports are unchanged.

## Prospect CRM

Shortlisted leads are stored as CRM records in the current Streamlit session. The Prospects page supports New, Contacted, Interested, Follow Up, Closed Won, and Closed Lost statuses, internal notes, contacted/follow-up dates, overdue follow-up indicators, and filters for status, no-website leads, and hot leads. Use **Export CRM CSV** to download business details and outreach tracking fields. There is no database; session CRM edits last for the active browser session.

## Opportunity Scores and Website Audits

Each business receives a deterministic 0-100 opportunity score: no website (+50), rating of at least 4.5 (+20), at least 100 reviews (+20), and a phone number (+10). Labels are HOT LEAD (90-100), HIGH OPPORTUNITY (70-89), MEDIUM (50-69), and LOW (0-49). Results can be filtered and sorted by these lead signals.

Website audits are opt-in and run only after selecting **Run Website Audit** for a specific business. Results are cached in the current Streamlit session by website URL; use **Re-run Website Audit** to explicitly refresh one. Audited checks include HTTPS, title, description, contact form, mobile viewport, and social links. Search and exports never trigger an audit. Audit fields are included in dashboard exports only for businesses audited during the session; the existing file exporter remains unchanged.

The detail dialog also reports observed reachability, response time, page title, and deterministic builder signatures (Wix, WordPress, Squarespace, Shopify, and Webflow). Undetected builders and unavailable page values are shown as `Unknown`. Desktop/mobile screenshots are fetched only when their individual preview buttons are pressed, then cached for the Streamlit session. The default replaceable screenshot provider uses Thum.io; screenshots therefore send the selected website URL to that provider. Replace `ThumIoScreenshotProvider` in `app/services/screenshot_provider.py` to use another provider.
