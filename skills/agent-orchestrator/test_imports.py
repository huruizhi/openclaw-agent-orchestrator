#!/usr/bin/env python3
"""Test that all required dependencies can be imported."""

import sys

def test_imports():
    """Test importing all required modules."""

    print("Testing dependencies...")
    print()

    # Test jsonschema
    try:
        from jsonschema import Draft202012Validator, ValidationError
        print("✓ jsonschema imported successfully")
    except ImportError as e:
        print(f"✗ jsonschema import failed: {e}")
        return False

    # Test dotenv
    try:
        from dotenv import load_dotenv
        print("✓ python-dotenv imported successfully")
    except ImportError as e:
        print(f"✗ python-dotenv import failed: {e}")
        return False

    # Test standard library modules (should always work)
    try:
        import json
        import os
        import urllib.request
        print("✓ Standard library modules OK")
    except ImportError as e:
        print(f"✗ Standard library import failed: {e}")
        return False

    print()
    print("=" * 50)
    print("All dependencies satisfied!")
    print("=" * 50)
    return True

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
