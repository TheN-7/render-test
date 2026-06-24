#!/usr/bin/env python3
"""
WoWS API integration for enhanced replay data extraction.

Requires:
    pip install requests

Configuration:
    Set your API credentials in environment variables or config file:
    - WWS_APP_ID: Your WoWS Application ID
    - WWS_REALM: Your server region (na, eu, asia, ru)
"""

import os
import requests
import json
import time
from pathlib import Path
from typing import Dict, Optional, List, Any
from dataclasses import dataclass

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "wws_api_config.json"
DEFAULT_SHIPS_CACHE_FILE = ROOT_DIR / "ships_cache.json"

@dataclass
class WoWSCredentials:
    app_id: str
    realm: str = "na"  # Default to North America
    base_url: str = None
    
    def __post_init__(self):
        if self.base_url is None:
            realm_urls = {
                "na": "https://api.worldofwarships.com/wows/",
                "eu": "https://api.worldofwarships.eu/wows/",
                "asia": "https://api.worldofwarships.asia/wows/",
                "ru": "https://api.worldofwarships.ru/wows/"
            }
            self.base_url = realm_urls.get(self.realm.lower(), realm_urls["na"])

class WoWSAPI:
    def __init__(self, credentials: WoWSCredentials):
        self.creds = credentials
        self.session = requests.Session()
        self.cache = {}  # Simple cache for API responses
        self.rate_limit_delay = 0.1  # 100ms between requests to respect rate limits
    
    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Optional[Dict]:
        """Make API request with rate limiting and error handling."""
        if params is None:
            params = {}
        
        params['application_id'] = self.creds.app_id
        
        # Check cache first
        cache_key = f"{endpoint}_{hash(str(sorted(params.items())))}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        url = f"{self.creds.base_url}{endpoint}"
        
        try:
            time.sleep(self.rate_limit_delay)  # Rate limiting
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Check API response status
            if data.get('status') == 'ok':
                result = data.get('data', {})
                self.cache[cache_key] = result
                return result
            else:
                error_msg = data.get('error', {}).get('message', 'Unknown API error')
                print(f"API Error: {error_msg}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return None
    
    def get_ship_info(self, ship_id: int) -> Optional[Dict]:
        """Get detailed information about a specific ship."""
        return self._make_request('encyclopedia/ships/', {'ship_id': ship_id})
    
    def get_all_ships(self) -> Optional[Dict]:
        """Get all ships in encyclopedia (handles pagination)."""
        all_ships = {}
        page = 1
        limit = 100
        
        while True:
            params = {
                'application_id': self.creds.app_id,
                'fields': 'name,tier,type,nation',  # Request additional fields
                'limit': limit,
                'page_no': page
            }
            
            result = self._make_request('encyclopedia/ships/', params)
            if not result:
                print(f"Failed to get page {page}")
                break
            
            # The result is already the ships dictionary (no 'data' wrapper)
            all_ships.update(result)
            
            # We need to make a separate call to get pagination info
            # Let's make a call without fields to get the meta info
            meta_params = {
                'application_id': self.creds.app_id,
                'limit': 1,  # Minimal request to get meta info
                'page_no': page
            }
            
            meta_response = self._make_request('encyclopedia/ships/', meta_params)
            if meta_response:
                # Get meta from a raw request to see pagination
                import requests
                try:
                    url = f"{self.creds.base_url}encyclopedia/ships/"
                    test_response = requests.get(url, params=meta_params, timeout=10)
                    if test_response.status_code == 200:
                        full_data = test_response.json()
                        meta = full_data.get('meta', {})
                        page_count = meta.get('page_total', 1)
                        total_count = meta.get('total', 0)
                    else:
                        # If we can't get meta, assume this is the last page
                        page_count = page
                        total_count = len(all_ships)
                except:
                    page_count = page
                    total_count = len(all_ships)
            else:
                page_count = page
                total_count = len(all_ships)
            
            print(f"Downloaded page {page} ({len(all_ships)} ships so far)")
            
            if page >= page_count or len(result) < limit:
                break
            
            page += 1
            
            # Add small delay to respect rate limits
            import time
            time.sleep(0.1)
        
        print(f"Completed downloading {len(all_ships)} ships")
        return all_ships
    
    def get_player_info(self, search_name: str) -> Optional[Dict]:
        """Search for player by name."""
        return self._make_request('account/list/', {'search': search_name, 'limit': 1})
    
    def get_player_stats(self, account_id: int) -> Optional[Dict]:
        """Get player statistics."""
        return self._make_request('account/stats/', {'account_id': account_id})
    
    def get_player_achievements(self, account_id: int) -> Optional[Dict]:
        """Get player achievements."""
        return self._make_request('account/achievements/', {'account_id': account_id})
    
    def get_clan_info(self, clan_id: int) -> Optional[Dict]:
        """Get clan information."""
        return self._make_request('clans/info/', {'clan_id': clan_id})
    
    def get_clan_glossary(self) -> Optional[Dict]:
        """Get all clans (useful for searching)."""
        return self._make_request('clans/glossary/')

def load_credentials() -> Optional[WoWSCredentials]:
    """Load API credentials from environment variables or config file."""
    app_id = os.getenv('WWS_APP_ID')
    realm = os.getenv('WWS_REALM', 'na')
    
    if not app_id:
        # Try to load from config file
        if CONFIG_FILE.exists():
            try:
                with CONFIG_FILE.open('r', encoding='utf-8') as f:
                    config = json.load(f)
                    app_id = config.get('app_id')
                    realm = config.get('realm', 'na')
            except Exception as e:
                print(f"Error reading config file: {e}")
    
    if not app_id:
        print("ERROR: WoWS API credentials not found!")
        print(f"Set WWS_APP_ID environment variable or create {CONFIG_FILE.name}")
        print("Example config file:")
        print('{"app_id": "your_app_id_here", "realm": "na"}')
        return None
    
    return WoWSCredentials(app_id=app_id, realm=realm)

def create_ship_cache(api: WoWSAPI, cache_file: str | Path | None = None) -> Dict[str, Dict]:
    """Create a local cache of ship information for faster lookups."""
    cache_path = Path(cache_file) if cache_file else DEFAULT_SHIPS_CACHE_FILE

    if cache_path.exists():
        try:
            with cache_path.open('r', encoding='utf-8') as f:
                cache_data = json.load(f)
                print(f"Loaded {len(cache_data)} ships from cache")
                return cache_data  # Return as-is to preserve string keys
        except Exception as e:
            print(f"Error loading ship cache: {e}")
    
    print("Downloading ship information from API...")
    ships_data = api.get_all_ships()
    
    if ships_data:
        print(f"Cached {len(ships_data)} ships to {cache_path}")
        with cache_path.open('w', encoding='utf-8') as f:
            json.dump(ships_data, f, indent=2)
        return ships_data
    
    return {}

# Ship name resolution helper
def get_ship_name(ship_id: int, ships_cache: Dict[str, Dict]) -> str:
    """Get human-readable ship name from cache."""
    ship_id_str = str(ship_id)  # Convert to string for dictionary key
    
    if ship_id_str in ships_cache:
        ship = ships_cache[ship_id_str]
        name = ship.get('name', f'Unknown ({ship_id})')
        # Clean special characters that might cause encoding issues
        try:
            name = name.encode('ascii', errors='ignore').decode('ascii')
        except:
            name = str(ship_id)  # Fallback to ID if name has issues
        
        tier = ship.get('tier', '')
        ship_type = ship.get('type', '').title()
        
        if tier and ship_type:
            return f"{name} (Tier {tier} {ship_type})"
        return name
    elif ship_id in ships_cache:  # Try numeric key as fallback
        ship = ships_cache[ship_id]
        name = ship.get('name', f'Unknown ({ship_id})')
        # Clean special characters
        try:
            name = name.encode('ascii', errors='ignore').decode('ascii')
        except:
            name = str(ship_id)
        
        tier = ship.get('tier', '')
        ship_type = ship.get('type', '').title()
        
        if tier and ship_type:
            return f"{name} (Tier {tier} {ship_type})"
        return name
    
    return f"Unknown ({ship_id})"

# Example usage
if __name__ == "__main__":
    # Load credentials and test API
    creds = load_credentials()
    if creds:
        api = WoWSAPI(creds)
        
        # Test getting ship info
        ship_id = 3759585072  # Example from your replay
        ship_info = api.get_ship_info(ship_id)
        if ship_info:
            print(f"Ship info for {ship_id}: {ship_info}")
        
        # Test player search
        player_name = "Florindi_1"
        player_info = api.get_player_info(player_name)
        if player_info:
            print(f"Player info: {player_info}")
