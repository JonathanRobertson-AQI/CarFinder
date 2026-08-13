"""Facebook Marketplace scraper.

Facebook Marketplace has no public API and requires a logged-in session for
most searches. This scraper expects the Playwright browser context to
already have a valid Facebook login (see README for how to provide a saved
`storage_state` file) -- it does not handle login itself.

Marketplace's DOM is heavily obfuscated (auto-generated class names) and
changes frequently, so selectors here are deliberately broad (role/text based
where possible) and this scraper should be expected to need maintenance.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from carfinder.models import Listing
from carfinder.scrapers.base import BaseScraper, parse_mileage, parse_price, parse_year


class FacebookMarketplaceScraper(BaseScraper):
    source_name = "facebook"

    def search_url(self) -> str:
        query = quote_plus(f"{self.config.make} {self.config.model}")
        # "propertyoftype=cars" search within Marketplace's vehicles category.
        base = f"https://www.facebook.com/marketplace/search/?query={query}"
        if self.config.price_max:
            base += f"&maxPrice={int(self.config.price_max)}"
        if self.config.price_min:
            base += f"&minPrice={int(self.config.price_min)}"
        return base

    def extract_listings(self, page) -> list[Listing]:
        listings: list[Listing] = []

        # Marketplace search results are anchors linking to /marketplace/item/...
        cards = page.locator("a[href*='/marketplace/item/']").all()
        seen_urls: set[str] = set()

        for card in cards:
            try:
                href = card.get_attribute("href") or ""
                if not href:
                    continue
                url = "https://www.facebook.com" + href.split("?")[0]
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                text = card.inner_text()
            except Exception:
                continue

            if not text:
                continue

            lines = [line.strip() for line in text.split("\n") if line.strip()]
            title = lines[1] if len(lines) > 1 else (lines[0] if lines else "")
            price = parse_price(lines[0]) if lines else None
            year = parse_year(title)

            listings.append(
                Listing(
                    source=self.source_name,
                    url=url,
                    title=title,
                    price=price,
                    year=year,
                    make=self.config.make,
                    model=self.config.model,
                    location=self.config.location,
                )
            )

        return listings
