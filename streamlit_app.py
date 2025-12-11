# streamlit_app.py - Minimal entry point
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Import and call main
from app import main

if __name__ == "__main__":
    main()