#!/bin/bash

# LaTeX to HTML Converter Startup Script

echo "Starting LaTeX to Accessible HTML Converter..."

# Check if Quarto and pandoc are installed
if ! command -v quarto &> /dev/null; then
    echo "Error: Quarto is not installed. Please install it first:"
    echo "  Visit: https://quarto.org/docs/get-started/"
    exit 1
fi

if ! command -v pandoc &> /dev/null; then
    echo "Error: pandoc is not installed. Please install it first:"
    echo "  macOS: brew install pandoc"
    exit 1
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed."
    exit 1
fi

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
if ! pip install -r requirements.txt; then
    echo "Error: Failed to install Python dependencies."
    exit 1
fi

# Create necessary directories
mkdir -p uploads output

echo "Starting Flask application on http://localhost:8000"
python app.py
