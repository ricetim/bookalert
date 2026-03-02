import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from config import ensure_config_file, load_config
from daemon import run_check_cycle, run_daemon
from db import add_book, get_connection, get_history, init_db, list_books, remove_book
from scraper import fetch_book

console = Console()


def _get_conn(cfg):
    db_path = Path(cfg["database"]["path"]).expanduser()
    conn = get_connection(db_path)
    init_db(conn)
    return conn


@click.group()
def main():
    """Bookalert — monitor book prices on bookfinder.com."""


@main.command()
@click.argument("isbn")
@click.argument("target_price", type=float)
def add(isbn: str, target_price: float):
    """Add a book by ISBN with a target price."""
    console.print(f"Fetching book info for ISBN [bold]{isbn}[/bold]…")
    result = fetch_book(isbn)

    if result.error and not result.found:
        console.print(f"[red]Error:[/red] {result.error}")
        sys.exit(1)

    title = result.title or f"ISBN {isbn}"
    author = result.author or "Unknown"

    cfg = load_config()
    with _get_conn(cfg) as conn:
        add_book(conn, isbn, title, author, target_price)

    if result.lowest_price is not None:
        cond_str = f" ({result.condition})" if result.condition else ""
        price_str = f"${result.lowest_price:.2f}{cond_str}"
    else:
        price_str = "N/A"
    console.print(f"[green]Added:[/green] {title} by {author}")
    console.print(f"  Current lowest price: {price_str}")
    console.print(f"  Target price: ${target_price:.2f}")


@main.command()
@click.argument("isbn")
def remove(isbn: str):
    """Remove a book (soft-delete; history preserved)."""
    cfg = load_config()
    with _get_conn(cfg) as conn:
        removed = remove_book(conn, isbn)
    if removed:
        console.print(f"[green]Removed[/green] ISBN {isbn}.")
    else:
        console.print(f"[yellow]ISBN {isbn} not found or already removed.[/yellow]")


@main.command("list")
def list_cmd():
    """List all monitored books with current prices."""
    cfg = load_config()
    with _get_conn(cfg) as conn:
        books = list_books(conn)

    if not books:
        console.print("No books being monitored. Use [bold]bookalert add[/bold] to add one.")
        return

    table = Table(show_lines=True, expand=True, padding=(0, 1))
    table.add_column("ISBN", style="cyan", no_wrap=True, min_width=13)
    table.add_column("Title / Author", ratio=3)
    table.add_column("Target", justify="right", style="yellow", no_wrap=True)
    table.add_column("Current", justify="right", no_wrap=True)
    table.add_column("Condition", ratio=2)
    table.add_column("Checked", no_wrap=True)

    for b in books:
        # Title + author in one cell
        title_author = Text(b["title"], style="bold")
        title_author.append(f"\n{b['author']}", style="dim")

        # Price
        current = f"${b['current_price']:.2f}" if b["current_price"] is not None else "—"
        target_below = (
            b["current_price"] is not None
            and b["current_price"] <= b["target_price"]
        )
        current_text = Text(current, style="green bold" if target_below else "")

        # Condition
        condition = b["current_condition"] or "—"

        # Date: show only date portion
        raw = b["price_as_of"] or ""
        checked = raw.split(" ")[0] if raw else "Never"

        table.add_row(
            b["isbn"],
            title_author,
            f"${b['target_price']:.2f}",
            current_text,
            condition,
            checked,
        )

    console.print(table)


@main.command()
@click.argument("isbn")
def history(isbn: str):
    """Show price history for a book."""
    cfg = load_config()
    with _get_conn(cfg) as conn:
        rows = get_history(conn, isbn)

    if not rows:
        console.print(f"No history for ISBN {isbn}.")
        return

    table = Table(title=f"Price History — {isbn}", show_lines=True)
    table.add_column("Checked At")
    table.add_column("Lowest Price", justify="right")
    table.add_column("Condition")
    table.add_column("At Target?", justify="center")

    for r in rows:
        price = f"${r['lowest_price']:.2f}" if r["lowest_price"] is not None else "N/A"
        condition = r["condition"] or "—"
        at_target = "[green]Yes[/green]" if r["available"] else "No"
        table.add_row(r["checked_at"], price, condition, at_target)

    console.print(table)


@main.command()
def check():
    """Run a price check cycle immediately."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )
    cfg = load_config()
    run_check_cycle(cfg)


@main.command()
def daemon():
    """Start the background daemon (used by systemd)."""
    ensure_config_file()
    run_daemon()
