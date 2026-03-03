import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for

from config import load_config
from daemon import run_check_cycle
from db import get_connection, init_db, add_book, remove_book, list_books, get_history, get_alerts, record_price, update_target_price
from scraper import fetch_book

log = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Config — INI with env var overrides
# ---------------------------------------------------------------------------

def _build_cfg():
    cfg = load_config()
    for env_var, (section, key) in {
        "BOOKALERT_DB_PATH":        ("database", "path"),
        "BOOKALERT_JOIN_API_KEY":   ("join",     "api_key"),
        "BOOKALERT_JOIN_DEVICE_ID": ("join",     "device_id"),
        "BOOKALERT_CHECK_INTERVAL": ("daemon",   "check_interval_minutes"),
        "BOOKALERT_BASE_URL":       ("web",      "base_url"),
    }.items():
        val = os.environ.get(env_var)
        if val:
            cfg[section][key] = val
    return cfg


cfg = _build_cfg()
db_path = Path(cfg["database"]["path"]).expanduser()


def _conn():
    conn = get_connection(db_path)
    init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# In-memory job store for background add-book tasks
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _run_add_job(job_id: str, isbn: str, target_price: float) -> None:
    try:
        result = fetch_book(isbn)
        if result.error or not result.found:
            err = result.error or "Book not found"
            with _jobs_lock:
                _jobs[job_id] = {"status": "error", "message": err}
            return

        with _conn() as conn:
            add_book(conn, isbn, result.title, result.author, target_price)
            record_price(conn, isbn, result.lowest_price, target_price, result.condition)

        price_str = f"${result.lowest_price:.2f}" if result.lowest_price is not None else "N/A"
        with _jobs_lock:
            _jobs[job_id] = {
                "status": "done",
                "isbn": isbn,
                "title": result.title,
                "author": result.author,
                "price": price_str,
                "target": f"${target_price:.2f}",
            }
    except Exception as exc:
        log.exception("Add job %s failed", job_id)
        with _jobs_lock:
            _jobs[job_id] = {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def books():
    with _conn() as conn:
        rows = list_books(conn)
    return render_template("books.html", books=rows)


@app.get("/add")
def add_form():
    return render_template("add.html")


@app.post("/add")
def add_submit():
    isbn = request.form.get("isbn", "").strip()
    target_raw = request.form.get("target_price", "").strip()

    errors = []
    if not isbn:
        errors.append("ISBN is required.")
    if not target_raw:
        errors.append("Target price is required.")
    else:
        try:
            target_price = float(target_raw)
            if target_price <= 0:
                errors.append("Target price must be positive.")
        except ValueError:
            errors.append("Target price must be a number.")

    if errors:
        return render_template("add.html", errors=errors, isbn=isbn, target_price=target_raw)

    target_price = float(target_raw)
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status": "pending"}

    t = threading.Thread(target=_run_add_job, args=(job_id, isbn, target_price), daemon=True)
    t.start()

    return render_template("pending.html", job_id=job_id, isbn=isbn)


@app.get("/add/poll/<job_id>")
def add_poll(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)

    if job is None:
        return render_template("_poll_done.html", status="error", message="Job not found."), 200

    if job["status"] == "pending":
        return render_template("_poll_pending.html", job_id=job_id, isbn="")

    # Terminal state — remove from store and return result
    with _jobs_lock:
        _jobs.pop(job_id, None)

    if job["status"] == "error":
        return render_template("_poll_done.html", status="error", message=job["message"])

    return render_template("_poll_done.html", status="done", job=job)


@app.get("/history/<isbn>")
def history(isbn: str):
    with _conn() as conn:
        rows = get_history(conn, isbn)
        book = conn.execute(
            "SELECT title, author, target_price FROM books WHERE isbn = ?", (isbn,)
        ).fetchone()

    if not rows and not book:
        return redirect(url_for("books"))

    reversed_rows = list(reversed(rows))
    chart_json = json.dumps({
        "labels": [r["checked_at"][:10] for r in reversed_rows],
        "prices": [r["lowest_price"] for r in reversed_rows],
    })

    return render_template(
        "history.html",
        isbn=isbn,
        book=book,
        rows=rows,
        chart_json=chart_json,
    )


@app.get("/alerts")
def alerts():
    with _conn() as conn:
        rows = get_alerts(conn)
    return render_template("alerts.html", alerts=rows)


@app.get("/target-display/<isbn>")
def target_display(isbn: str):
    with _conn() as conn:
        book = conn.execute(
            "SELECT target_price FROM books WHERE isbn = ? AND active = 1", (isbn,)
        ).fetchone()
    if not book:
        return "", 404
    return render_template("_target_display.html", isbn=isbn, target_price=book["target_price"])


@app.get("/edit-target/<isbn>")
def edit_target(isbn: str):
    with _conn() as conn:
        book = conn.execute(
            "SELECT target_price FROM books WHERE isbn = ? AND active = 1", (isbn,)
        ).fetchone()
    if not book:
        return "", 404
    return render_template("_target_edit.html", isbn=isbn, target_price=book["target_price"])


@app.post("/update-target/<isbn>")
def update_target(isbn: str):
    raw = request.form.get("target_price", "").strip()
    try:
        price = float(raw)
        if price <= 0:
            raise ValueError("non-positive")
    except ValueError:
        return "Invalid price", 400
    with _conn() as conn:
        update_target_price(conn, isbn, price)
    return render_template("_target_display.html", isbn=isbn, target_price=price)


@app.post("/remove/<isbn>")
def remove(isbn: str):
    with _conn() as conn:
        remove_book(conn, isbn)
    return "", 200


# ---------------------------------------------------------------------------
# Background daemon thread
# ---------------------------------------------------------------------------

def _daemon_loop():
    interval = int(cfg["daemon"]["check_interval_minutes"]) * 60
    log.info("Bookalert web daemon started. Checking every %d minutes.", interval // 60)
    while True:
        try:
            run_check_cycle(cfg)
        except Exception:
            log.exception("daemon cycle error")
        time.sleep(interval)


# Guard against Flask debug reloader spawning two threads:
# In debug mode the reloader spawns a child process with WERKZEUG_RUN_MAIN=true;
# only that child (or any non-debug run) should start the daemon.
_debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
if not _debug_mode or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    threading.Thread(target=_daemon_loop, daemon=True, name="bookalert-daemon").start()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug)
