#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python --version
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
printf '%s\n' 'Installed. Run ./rt82 --help.'
