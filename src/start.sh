#!/usr/bin/env bash

cd /lipsync
python3.11 -u ./main.py &
python3.11 -u /handler.py