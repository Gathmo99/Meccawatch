#!/usr/bin/env python3
"""Send an ad-hoc message to Discord and/or Telegram."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from watcher import notify_all  # reuses the same webhook/bot config + truncation logic

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: notify.py <message>", file=sys.stderr)
        raise SystemExit(1)
    notify_all([" ".join(sys.argv[1:])])
    print("sent")
