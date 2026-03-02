import configparser
import logging
import signal
import time
from pathlib import Path

from config import load_config
from db import get_connection, get_active_books, init_db, record_price
from notifier import send_notification
from scraper import fetch_book

log = logging.getLogger(__name__)


def run_check_cycle(cfg: configparser.ConfigParser) -> None:
    db_path = Path(cfg["database"]["path"]).expanduser()
    api_key = cfg["join"]["api_key"]
    device_id = cfg["join"]["device_id"]

    with get_connection(db_path) as conn:
        init_db(conn)
        books = get_active_books(conn)
        log.info("Starting check cycle for %d book(s).", len(books))

        for book in books:
            isbn = book["isbn"]
            title = book["title"]
            author = book["author"]
            target = book["target_price"]

            log.info("Checking ISBN %s — %s (target $%.2f)", isbn, title, target)
            result = fetch_book(isbn)

            if result.error:
                log.warning("Scrape error for %s: %s", isbn, result.error)
                # Still record as unavailable so history is continuous
                record_price(conn, isbn, None, target)
                continue

            price_str = f"${result.lowest_price:.2f}" if result.lowest_price is not None else "N/A"
            cond_str = f" ({result.condition})" if result.condition else ""
            log.info("  Lowest price: %s%s", price_str, cond_str)

            available = record_price(conn, isbn, result.lowest_price, target, result.condition)

            if available:
                log.info("  Target met — sending notification.")
                if api_key and device_id:
                    sent = send_notification(
                        api_key,
                        device_id,
                        title,
                        author,
                        result.lowest_price,
                        target,
                        result.condition,
                    )
                    if sent:
                        log.info("  Notification sent.")
                    else:
                        log.warning("  Notification failed.")
                else:
                    log.warning("  Join api_key/device_id not configured — skipping notification.")

    log.info("Check cycle complete.")


def run_daemon() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    cfg = load_config()
    interval_minutes = int(cfg["daemon"]["check_interval_minutes"])
    interval_seconds = interval_minutes * 60

    running = True

    def _stop(signum, frame):
        nonlocal running
        log.info("Received signal %s, shutting down.", signum)
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("Bookalert daemon started. Checking every %d minutes.", interval_minutes)

    while running:
        try:
            run_check_cycle(cfg)
        except Exception:
            log.exception("Unexpected error in check cycle.")

        # Sleep in 1-second increments so SIGTERM is handled promptly
        elapsed = 0
        while running and elapsed < interval_seconds:
            time.sleep(1)
            elapsed += 1

    log.info("Bookalert daemon stopped.")
