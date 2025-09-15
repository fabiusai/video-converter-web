#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Aggiorna i pacchetti del sistema e installa ffmpeg
apt-get update -y
apt-get install -y ffmpeg

# 2. Installa le dipendenze Python
pip install -r requirements.txt
