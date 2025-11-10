#!/bin/bash

apt-get update -y
apt-get install -y ffmpeg

pip install -r requirements.txt

gunicorn server:app --bind 0.0.0.0:$PORT
