#!/usr/bin/env python3
"""
Setup script for WoWS API integration.

This script helps you configure your API credentials and tests the connection.
"""

import os
import json
import sys
from pathlib import Path

try:
    from .wows_api import load_credentials, WoWSAPI, create_ship_cache
except ImportError:
    from wows_api import load_credentials, WoWSAPI, create_ship_cache

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "wws_api_config.json"
SHIP_CACHE_FILE = ROOT_DIR / "ships_cache.json"

def setup_credentials():
    """Interactive setup for API credentials."""
    print("WoWS API Setup")
    print("=" * 50)
    print("This script will help you configure your WoWS API credentials.")
    print()
    
    # Get API Application ID
    app_id = input("Enter your WoWS Application ID: ").strip()
    if not app_id:
        print("ERROR: Application ID is required!")
        return False
    
    # Get realm
    print("\nAvailable realms:")
    print("  na - North America")
    print("  eu - Europe") 
    print("  asia - Asia")
    print("  ru - Russia")
    
    realm = input("Enter your realm (default: na): ").strip().lower()
    if not realm:
        realm = "na"
    elif realm not in ["na", "eu", "asia", "ru"]:
        print("WARNING: Invalid realm, using 'na'")
        realm = "na"
    
    # Save to config file
    config = {
        "app_id": app_id,
        "realm": realm
    }
    
    try:
        with CONFIG_FILE.open('w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        print(f"SUCCESS: Configuration saved to {CONFIG_FILE.name}")
    except Exception as e:
        print(f"ERROR: Error saving config: {e}")
        return False
    
    # Test the configuration
    print("\nTesting API connection...")
    try:
        creds = load_credentials()
        if creds:
            api = WoWSAPI(creds)
            
            # Test API with a simple request
            ships_data = api.get_all_ships()
            if ships_data:
                print(f"SUCCESS: API connection successful!")
                print(f"   Retrieved {len(ships_data)} ships from encyclopedia")
                
                # Test ship lookup
                if len(ships_data) > 0:
                    sample_ship_id = list(ships_data.keys())[0]
                    sample_ship = ships_data[sample_ship_id]
                    print(f"   Sample ship: {sample_ship.get('name', 'Unknown')}")
                
                return True
            else:
                print("ERROR: API test failed - no data returned")
                return False
        else:
            print("ERROR: Could not load credentials")
            return False
            
    except Exception as e:
        print(f"ERROR: API test failed: {e}")
        return False

def create_ship_cache_interactive():
    """Create ship cache with progress indication."""
    print("\nCreating ship cache...")
    
    creds = load_credentials()
    if not creds:
        print("ERROR: API credentials not configured!")
        return False
    
    api = WoWSAPI(creds)
    ships_cache = create_ship_cache(api, str(SHIP_CACHE_FILE))
    
    if ships_cache:
        print(f"SUCCESS: Ship cache created with {len(ships_cache)} ships")
        return True
    else:
        print("ERROR: Failed to create ship cache")
        return False

def show_status():
    """Show current configuration status."""
    print("Current Configuration Status")
    print("=" * 50)
    
    # Check environment variables
    app_id_env = os.getenv('WWS_APP_ID')
    realm_env = os.getenv('WWS_REALM')
    
    if app_id_env:
        print(f"SUCCESS: Environment variables configured:")
        print(f"   WWS_APP_ID: {app_id_env[:8]}...{app_id_env[-4:]}")
        print(f"   WWS_REALM: {realm_env or 'na'}")
    else:
        print("INFO: No environment variables found")
    
    # Check config file
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open('r', encoding='utf-8') as f:
                config = json.load(f)
            app_id = str(config.get('app_id') or '')
            if app_id:
                masked = f"{app_id[:8]}...{app_id[-4:]}"
            else:
                masked = "Not set"
            print(f"SUCCESS: Config file found: {CONFIG_FILE.name}")
            print(f"   App ID: {masked}")
            print(f"   Realm: {config.get('realm', 'Not set')}")
        except Exception as e:
            print(f"ERROR: Error reading config file: {e}")
    else:
        print("INFO: No config file found")
    
    # Check ship cache
    if SHIP_CACHE_FILE.exists():
        try:
            with SHIP_CACHE_FILE.open('r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"SUCCESS: Ship cache found: {len(cache)} ships")
        except Exception as e:
            print(f"ERROR: Error reading ship cache: {e}")
    else:
        print("INFO: No ship cache found")

def main():
    print("WoWS Replay Tools - API Setup")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "setup":
            if setup_credentials():
                create_ship_cache_interactive()
        elif command == "test":
            creds = load_credentials()
            if creds:
                api = WoWSAPI(creds)
                ships_data = api.get_all_ships()
                if ships_data:
                    print(f"SUCCESS: API working! Found {len(ships_data)} ships")
                else:
                    print("ERROR: API test failed")
            else:
                print("ERROR: No credentials found")
        elif command == "cache":
            create_ship_cache_interactive()
        elif command == "status":
            show_status()
        else:
            print("Available commands:")
            print("  setup  - Interactive setup")
            print("  test   - Test API connection")
            print("  cache  - Create ship cache")
            print("  status - Show current status")
    else:
        print("Usage:")
        print("  python setup_api.py setup   - Interactive setup")
        print("  python setup_api.py test    - Test API connection")
        print("  python setup_api.py cache   - Create ship cache")
        print("  python setup_api.py status  - Show current status")
        print()
        show_status()

if __name__ == "__main__":
    main()
