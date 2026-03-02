# Bookalert

Bookalert monitors book prices on [Bookfinder.com](https://www.bookfinder.com) and sends push notifications via the [Join](https://joaoapps.com/join/) Android app when a book drops to your target price. It includes a dark web UI (Readarr/Sonarr-style) and runs as a Docker container.

---

## Features

- Add books by ISBN with a target price
- Checks prices every 30 minutes via a background daemon
- Push notification to Android when a book hits your price
- Web UI with price history charts and alert log
- Docker-ready

---

## Docker (recommended)

### 1. Pull the image

```bash
docker pull timhrice/bookalert:latest
```

### 2. Add to your `docker-compose.yml`

```yaml
services:
  bookalert:
    image: timhrice/bookalert:latest
    container_name: bookalert
    restart: unless-stopped
    ports:
      - 5001:5000
    volumes:
      - /path/to/data:/data
    environment:
      BOOKALERT_DB_PATH: /data/bookalert.db
      BOOKALERT_JOIN_API_KEY: ""       # your Join API key
      BOOKALERT_JOIN_DEVICE_ID: ""     # your Join device ID
      BOOKALERT_CHECK_INTERVAL: "30"   # minutes between checks
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### 3. Start it

```bash
docker compose up -d bookalert
```

Open **http://yourserver:5001** in your browser.

---

## Join Push Notifications

1. Install [Join](https://play.google.com/store/apps/details?id=com.joaomgcd.join) on your Android device
2. Get your API key and device ID from [joinjoaomgcd.com](https://joinjoaomgcd.com)
3. Set `BOOKALERT_JOIN_API_KEY` and `BOOKALERT_JOIN_DEVICE_ID` in your environment or config file

---

## Running locally (without Docker)

### Requirements

- Python 3.9+
- Playwright (Chromium)

### Install

```bash
git clone https://github.com/ricetim/bookalert.git
cd bookalert
pip install -e .
playwright install chromium
```

### Configure

```bash
# Creates ~/.config/bookalert/config.ini
bookalert check
```

Edit `~/.config/bookalert/config.ini` and set your Join API key and device ID:

```ini
[join]
api_key = your_api_key_here
device_id = your_device_id_here

[daemon]
check_interval_minutes = 30

[database]
path = ~/.local/share/bookalert/bookalert.db
```

### Web UI

```bash
python web.py
# Open http://localhost:5000
```

### CLI

```bash
bookalert add <isbn> <target_price>    # add a book to monitor
bookalert list                          # show all monitored books
bookalert remove <isbn>                 # stop monitoring a book
bookalert history <isbn>               # show price history
bookalert check                        # run a price check now
bookalert daemon                       # run the background daemon
```

### systemd (optional)

```bash
cp bookalert.service ~/.config/systemd/user/
systemctl --user enable --now bookalert
journalctl --user -u bookalert -f
```

---

## Building from source

```bash
git clone https://github.com/ricetim/bookalert.git
cd bookalert
sudo docker build -t bookalert:latest .
```

---

## Tech stack

- Python 3.12
- Playwright (Chromium) — WAF-bypass scraping of Bookfinder
- SQLite — price history and book database
- Flask 3 + Jinja2 — web UI
- Bootstrap 5.3 dark theme + HTMX + Chart.js
- Join API — Android push notifications
