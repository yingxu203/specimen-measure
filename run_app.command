#!/bin/bash
# Double-click this file in Finder to launch the specimen-measure app in
# your browser. No command-line experience needed.
cd "$(dirname "$0")"

# Streamlit's very first run on a machine blocks waiting for an email
# address (or an empty Enter) at this exact prompt before it will start the
# server. Pre-writing an empty answer skips that prompt so double-clicking
# this file always launches straight into the app.
mkdir -p ~/.streamlit
if [ ! -f ~/.streamlit/credentials.toml ]; then
  printf '[general]\nemail = ""\n' > ~/.streamlit/credentials.toml
fi

python3 -m pip install --quiet -r requirements.txt
python3 -m streamlit run app.py
