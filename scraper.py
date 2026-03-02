import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

SEARCH_URL = "https://www.bookfinder.com/search/?isbn={isbn}&st=xl&ac=qr&submit="


@dataclass
class ScrapeResult:
    found: bool = False
    title: str = ""
    author: str = ""
    lowest_price: Optional[float] = None
    condition: str = ""
    error: str = ""


def fetch_book(isbn: str) -> ScrapeResult:
    url = SEARCH_URL.format(isbn=isbn)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            try:
                page.goto(url, wait_until="networkidle", timeout=60_000)
                if page.locator("#challenge-container").count() > 0:
                    page.wait_for_selector(
                        "#challenge-container", state="detached", timeout=20_000
                    )
                    page.wait_for_load_state("networkidle", timeout=30_000)
                html = page.content()
            except PlaywrightTimeout:
                return ScrapeResult(error=f"Timeout loading {url}")
            finally:
                browser.close()
    except Exception as e:
        return ScrapeResult(error=f"Browser error: {e}")
    return _parse(html)


def _parse(html: str) -> ScrapeResult:
    soup = BeautifulSoup(html, "html.parser")

    # Title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # Author — first sibling div after h1 whose text starts with "by"
    author = ""
    if h1:
        for sib in h1.next_siblings:
            if not hasattr(sib, "get_text"):
                continue
            text = sib.get_text(strip=True)
            if text.startswith("by"):
                author = text[2:].strip()
                break

    # Listings — each buy/rental row is a div.bg-white.p-[12px] card.
    # Rental listings carry "Rental - N days" in their text; skip them.
    # Each card appears twice (mobile + desktop layout), so deduplicate by (price, condition).
    seen: set[tuple[float, str]] = set()
    listings: list[tuple[float, str]] = []

    for card in soup.find_all(
        "div", class_=lambda c: c and "bg-white" in c and "p-[12px]" in c
    ):
        card_text = card.get_text(strip=True)

        if re.search(r"Rental\s*-\s*\d+\s*days", card_text):
            continue

        # First font-bold span with a dollar amount is the listing price
        price: Optional[float] = None
        for span in card.find_all("span", class_="font-bold"):
            m = re.fullmatch(r"\$([\d,]+\.\d{2})", span.get_text(strip=True))
            if m:
                try:
                    price = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass
                break

        if not price:
            continue

        # Condition
        if "NewBuy" in card_text:
            condition = "New"
        else:
            cm = re.search(r"Condition:(.+?)(?=\$)", card_text)
            if cm:
                condition = cm.group(1).strip()
            elif "UsedBuy" in card_text:
                condition = "Used"
            else:
                condition = "Unknown"

        key = (price, condition)
        if key not in seen:
            seen.add(key)
            listings.append(key)

    lowest_price: Optional[float] = None
    condition = ""
    if listings:
        cheapest = min(listings, key=lambda x: x[0])
        lowest_price, condition = cheapest

    found = bool(title) or lowest_price is not None
    if not found:
        return ScrapeResult(found=False, error="No results found")

    return ScrapeResult(
        found=found,
        title=title,
        author=author,
        lowest_price=lowest_price,
        condition=condition,
    )
