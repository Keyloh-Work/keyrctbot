#!/bin/bash

# Start the HTTP server in the background
python3 -m http.server 8000 &

# Start the Discord bot
python3 bot.py
