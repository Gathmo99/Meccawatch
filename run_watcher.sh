#!/bin/bash
cd ~/Meccawatch
set -a
source .env
set +a
./venv/bin/python watcher.py >> ~/Meccawatch/watcher.log 2>&1
if ! git diff --quiet snapshot.html state.json snapshots history artifacts 2>/dev/null; then
  git add snapshot.html state.json snapshots history artifacts
  git commit -m "A.R.G.U.S. website change detected (pi)" >> ~/Meccawatch/watcher.log 2>&1
fi
