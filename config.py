import configparser
from pathlib import Path

CONFIG_PATH = Path("~/.config/bookalert/config.ini").expanduser()

DEFAULTS = {
    "join": {
        "api_key": "",
        "device_id": "",
    },
    "daemon": {
        "check_interval_minutes": "30",
    },
    "database": {
        "path": "~/.local/share/bookalert/bookalert.db",
    },
}


def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    for section, values in DEFAULTS.items():
        cfg[section] = values
    cfg.read(CONFIG_PATH)
    return cfg


def ensure_config_file() -> None:
    if CONFIG_PATH.exists():
        return
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = configparser.ConfigParser()
    for section, values in DEFAULTS.items():
        cfg[section] = values
    with CONFIG_PATH.open("w") as f:
        cfg.write(f)
    print(f"Created default config at {CONFIG_PATH}")
    print("Edit it to set your Join api_key and device_id before using the daemon.")
