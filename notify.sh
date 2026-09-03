#!/bin/bash
cd ~/Meccawatch
set -a
source .env
set +a
./venv/bin/python notify.py "$@"
