#!/bin/bash
set -e
cd ~/Meccawatch
python3 - << "PYEOF"
import json
from pathlib import Path

state_file = Path("state.json")
state = json.loads(state_file.read_text(encoding="utf-8"))
state.pop("last_heartbeat_at", None)
state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
PYEOF
./run_watcher.sh
