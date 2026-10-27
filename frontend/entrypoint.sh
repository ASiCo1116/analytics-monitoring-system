#!/bin/bash
# Container start-up. The runtime image has no pixi, so run the same command as the pixi task directly.
set -e

source /shell-hook.sh

exec streamlit run app.py --server.address 0.0.0.0 --server.port 8501
