#!/bin/bash
# Start script for osu!lounge API server

cd "$(dirname "$0")"

echo "Starting osu!lounge API server..."
node server.js
