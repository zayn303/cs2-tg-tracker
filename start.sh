#!/bin/bash
# Simple startup script for Telegram Market Tracker Bot

# Create virtual environment if it doesn't exist or is broken
if [ ! -f "venv/bin/python" ]; then
    echo "Creating virtual environment..."
    rm -rf venv  # Clean up any broken venv
    python3 -m venv venv

    echo "Installing dependencies..."
    venv/bin/pip install --upgrade pip
    venv/bin/pip install -r requirements.txt
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo "ERROR: .env file not found!"
    echo ""
    echo "Create .env file:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    echo "  # Add your tokens and save"
    echo ""
    exit 1
fi

# Run bot using virtual environment
echo "Starting Telegram bot..."
echo "Press Ctrl+C to stop"
echo ""
venv/bin/python tg_bot.py
