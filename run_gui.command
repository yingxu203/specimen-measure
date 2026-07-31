#!/bin/bash
# Double-click this file in Finder to launch the specimen-measure desktop
# window (no browser, no command line needed).
cd "$(dirname "$0")"
python3 -m pip install --quiet -r requirements.txt
python3 specimen_measure_gui.py
