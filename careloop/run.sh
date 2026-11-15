#!/bin/bash
cd "$(dirname "$0")"
PY=python3
command -v python3 >/dev/null || PY=python
$PY -m pip install -r requirements.txt
$PY app.py
