#!/usr/bin/env python3
"""Send an ad-hoc message to the configured Discord webhook."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from watcher import send_discord  # reuses the same webhook + truncation logic

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: notify.py <message>", file=sys.stderr)
        raise SystemExit(1)
    send_discord([" ".join(sys.argv[1:])])
    print("sent")
