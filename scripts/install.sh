#!/usr/bin/env bash
#
# Install script for Nexus AI Assistant (Linux/macOS)
# Creates a virtual environment, installs dependencies,
# and optionally adds the nexus command to PATH.
#

set -e

echo "=== Nexus Installation (Linux/macOS) ==="

# Check if Python 3 is installed
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "ERROR: Python not found. Please install Python 3.9+."
    exit 1
fi

py_version=$($PYTHON --version 2>&1)
echo "Found: $py_version"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -e project/

# Copy .env if not exists
if [ ! -f "config/.env" ]; then
    echo "Creating .env from .env.example..."
    cp config/.env.example config/.env
    echo "NOTE: Edit config/.env and add your GROQ_API_KEY."
else
    echo ".env file already exists."
fi

# Add to PATH (optional)
SHELL_CONFIG="$HOME/.bashrc"
if [ -f "$HOME/.zshrc" ]; then
    SHELL_CONFIG="$HOME/.zshrc"
fi

if ! grep -q "nexus.*venv/bin" "$SHELL_CONFIG" 2>/dev/null; then
    echo ""
    echo "Do you want to add the nexus command to your PATH? (y/n)"
    read -r answer
    if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
        echo "export PATH=\"\$PATH:$PWD/venv/bin\"" >> "$SHELL_CONFIG"
        echo "Added to $SHELL_CONFIG. Run 'source $SHELL_CONFIG' to apply."
    fi
else
    echo "PATH already configured in $SHELL_CONFIG."
fi

echo ""
echo "=== Installation complete! ==="
echo "Before using, edit config/.env and add your GROQ_API_KEY."
echo ""
echo "Quick test:"
echo "  source venv/bin/activate"
echo '  nexus run "Привет!"'