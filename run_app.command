#!/bin/bash
# Double-click this file in Finder to launch the heart-measure app in your
# browser. No command-line experience needed.
cd "$(dirname "$0")"
python3 -m pip install --quiet -r requirements.txt
python3 -m streamlit run app.py
