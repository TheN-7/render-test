# Render Bot

Render Bot is a World of Warships replay toolset centered on a Discord bot that turns `.wowsreplay` files into animated minimap videos.

The main use case is simple:

- upload a replay with `/render` to get a single-player minimap MP4
- upload two replays from the same battle with `/render_dual` to get a synchronized side-by-side MP4


## What The Project Does

- Reads World of Warships replay files (`.wowsreplay`)
- Extracts canonical replay data from the binary replay format
- Renders animated minimap videos as MP4 files
- Supports dual-replay comparison renders from both teams
- Generates entity, battle-stat, and comprehensive analysis outputs
- Optionally uses WoWS API credentials and ship caches for richer metadata

## Main Entry Points

- `bot.py`
  Runs the Discord bot and exposes the slash commands.
- `main.py`
  Runs the local CLI tools for replay extraction and analysis.

## Main Commands

### Discord Commands

- `/render`
  Upload one replay and get back a minimap MP4.
- `/render_dual`
  Upload two replays from the same battle and get back a synchronized side-by-side MP4.

### CLI Commands

```bash
python main.py extract replay.wowsreplay
python main.py extract replay.wowsreplay replay.json --legacy replay_legacy.json
python main.py analyze replay.wowsreplay
python main.py entities replay.json
python main.py battle-stats replay.json
python main.py comprehensive replay.json --output analysis_results
python main.py setup
python main.py status
python main.py update-render baseline_supported_replay.wowsreplay candidate_new_version_replay.wowsreplay
```

What they do:

- `extract`
  Converts a replay into canonical JSON. Optionally writes a legacy-style JSON export too.
- `analyze`
  Runs the full analysis flow. If you pass a `.wowsreplay`, it first extracts canonical JSON and then runs the comprehensive analyzer.
- `entities`
  Produces entity-focused output from replay JSON.
- `battle-stats`
  Produces battle statistics from replay JSON.
- `comprehensive`
  Produces combined analysis output files in one pass.
- `setup`
  Configures WoWS API credentials and refreshes the ship cache.
- `status`
  Shows API and cache status.
- `update-render`
  Scaffolds support for a new replay version and refreshes the main render data files in one pass.

## Project Layout

```text
bot.py                  Discord bot entry point
main.py                 CLI entry point
minimap_render_v2.py    MP4 render pipeline
api/                    WoWS API setup and cache utilities
core/                   Replay extraction and canonical data logic
renderers/              Minimap rendering helpers
tools/dev_tools/        Replay analysis tools
tests/                  Regression and pipeline tests
content/                Extracted or generated content used by rendering
gui/                    UI assets such as ship icons, silhouettes, and map assets
vendor/                 Vendored support code
```


## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Core dependencies used by this repo include:

- `discord.py`
- `Pillow`
- `numpy`
- `imageio`
- `imageio-ffmpeg`
- `wowsunpack`

### 2. Make Sure MP4 Encoding Is Available

The renderer needs an FFmpeg-compatible encoder.

- If `ffmpeg` is already in your PATH, the project can use it directly.
- Otherwise, `imageio-ffmpeg` can provide the encoder binary.

### 3. Create `bot_config.json`

The bot expects a `bot_config.json` file in the repo root.

Example:

```json
{
  "token": "YOUR_DISCORD_BOT_TOKEN",
  "render_profile": "hosted",
  "render_quality": 1.0,
  "render_preset": "medium",
  "render_crf": "19",
  "render_fps": 30
}
```



### 4. Optional: Configure WoWS API Access

If you want API-backed metadata and cache refreshes:

```bash
python main.py setup
python main.py status
```

This creates or updates:

- `wws_api_config.json`
- `ships_cache.json`

Rendering does not depend on API setup to work, but API and cache data can improve metadata and related enrichment.

### Discord Render Workflow

1. Start the bot with `python bot.py`
2. Upload a replay with `/render`
3. Wait for the render queue to process it
4. Receive an MP4 in Discord

The bot automatically picks a Discord render profile from the server upload limit:

- `10 MB` or less: safe profile
- above `10 MB`: boosted profile
- above `50 MB`: HQ profile

### Dual Render Workflow

1. Collect two replay files from the same battle
2. Run `/render_dual`
3. Upload both files
4. Receive a synchronized side-by-side MP4

### Offline Analysis Workflow

1. Extract replay data:

```bash
python main.py extract replay.wowsreplay
```

2. Run a focused or full analysis:

```bash
python main.py entities replay.json
python main.py battle-stats replay.json
python main.py comprehensive replay.json --output analysis_results
```

## Updating The Render For A New WoWS Version

There are usually two things to refresh:

- replay parsing support for the new replay version
- render metadata/assets such as `GameParams.data`, aircraft mappings, and consumable ranges

### Fast Path: One Command

If your local assets are already refreshed for the new WoWS patch, run this first:

```bash
python main.py update-render baseline_supported_replay.wowsreplay candidate_new_version_replay.wowsreplay
```

What this updates in order:

- unpacked client assets used by the render
- replay-version support report and vendor scaffold
- `ships_cache.json`
- `content/ships_gameparams.json`
- `aircraft_params.json`
- `content/ship_consumables.json`
- `content/ship_aircraft_support.json`
- `content/gameparams_consumables.json`
- `content/overviewmaps.txt` from `gui/spaces/overviewmaps.txt`

The asset refresh also carries forward unpacked client `texts` into `content/texts` so the ship-catalog rebuild can use official in-client ship names right after a patch.

By default the command reads the WoWS install root from `game.path`, uses `wowsunpack` to refresh the render asset files it depends on, and then rebuilds the JSON/cache files on top of that.

The asset refresh is additive:

- existing files are updated in place if newer versions are found
- new files are copied in if the game added them
- files already in the repo are not deleted automatically

This is intentional so an interrupted refresh or a partial asset source does not remove working render assets.

The runtime render now uses `gui/ship_icons` and `gui/ships_silhouettes` for the player-card ship art path.
If a patch adds ships that only exist as preview art in the unpacked assets, you can backfill silhouettes after the asset refresh step with:

```bash
powershell -ExecutionPolicy Bypass -File .\tools\backfill_ship_silhouettes.ps1
```

This creates matching entries in `gui/ships_silhouettes` for preview-only ships so the render can stay on the silhouette-only asset path.

Useful options:

```bash
python main.py update-render baseline_supported_replay.wowsreplay candidate_new_version_replay.wowsreplay --dump-render-packets
python main.py update-render baseline_supported_replay.wowsreplay candidate_new_version_replay.wowsreplay --skip-ships-cache
python main.py update-render baseline_supported_replay.wowsreplay candidate_new_version_replay.wowsreplay --skip-assets
python main.py update-render baseline_supported_replay.wowsreplay candidate_new_version_replay.wowsreplay --gameparams .\content\GameParams.data
python main.py update-render baseline_supported_replay.wowsreplay candidate_new_version_replay.wowsreplay --assets-root D:\wows_unpacked
```

Use `--skip-ships-cache` if you want an offline refresh of the render data files without touching the WoWS API.
Use `--skip-assets` if you already refreshed the unpacked client assets separately.
Use `--assets-root` if you already have an unpacked client tree and want to copy from that instead of unpacking directly from the installed game.

### Manual Workflow

Use this workflow if you want to run the steps one by one.

### 1. Update Local Game Assets

Refresh the local game assets used by the renderer before testing the new version.

If the patch changed maps, icons, consumables, aircraft, or GameParams-derived data, update those assets first.
The one-command `update-render` flow now does this automatically unless you pass `--skip-assets`.

### 2. Generate A Replay-Version Update Report

Use one replay from the last supported version and one replay from the new version:

```bash
python tools/update_wows_version.py baseline_supported_replay.wowsreplay candidate_new_version_replay.wowsreplay --dump-render-packets
```

What this does:

- detects the candidate replay version
- compares packet shapes against the last supported replay
- creates a report in `replay_debug/version_updates/...`
- may scaffold a new folder under `vendor/replay_unpack/clients/wows/versions/`

Check the output for:

- `Folder created: True/False`
- `Manual review: True/False`
- `Report written to: ...`

If `Manual review: True`, inspect the generated report and packet dumps before trusting the new version.

### 2.5. Optional: Backfill Missing Ship Silhouettes

If the new patch added ships whose art exists only under `gui/ship_previews`, generate silhouettes for them:

```bash
powershell -ExecutionPolicy Bypass -File .\tools\backfill_ship_silhouettes.ps1
```

This is usually only needed when WG adds new ships and the unpacked client includes preview art before a matching silhouette/icon file appears in the repo.

### 3. Refresh Ship Catalog From GameParams And Texts

Rebuild the GameParams-native ship catalog used as a patch-day fallback for names, type, tier, and nation:

```bash
python tools/build_ships_gameparams.py
```

This refreshes `content/ships_gameparams.json` from:

- `content/GameParams.data`
- `content/texts`

The renderer still prefers `ships_cache.json` when available, but this catalog gives it an authoritative fallback when the WoWS API lags behind new client ships.

### 4. Refresh Aircraft Mapping From GameParams

Aircraft type mapping should be rebuilt from the latest `GameParams.data`:

```bash
python tools/rebuild_aircraft_params_from_gameparams.py
```

This updates `aircraft_params.json` from the authoritative game data.

### 5. Refresh Ship Consumables Reference

Rebuild the ship-by-ship consumables reference from the latest `GameParams.data`:

```bash
python tools/build_ship_consumables_from_gameparams.py
```

This refreshes `content/ship_consumables.json`, keyed by ship ID, so the render can verify which consumables each ship is actually allowed to have.

### 6. Refresh Ship Aircraft Support Reference

Rebuild the ship-by-ship aircraft support reference used for cautious squadron fallback typing:

```bash
python tools/build_ship_aircraft_support.py
```

This refreshes `content/ship_aircraft_support.json`, combining ship consumable plane support and aircraft-capable module metadata so the render can make safer fighter/spotter/hybrid fallback decisions.

Optional: if you also want to refresh the broader ship metadata cache used for names, modules, and stats, run:

```bash
python ships.py --update-cache
```

### 7. Refresh Radar/Hydro Consumable Data

If consumable definitions changed, rebuild the consumable extract used by the renderer:

```bash
python tools/extract_gameparams_consumables.py --gameparams .\content\GameParams.data --out .\content\gameparams_consumables.json
```

This refreshes the radar/hydro ranges and durations used by the render overlays.

### 7. Run A Sanity Render

Before updating the bot in production, render at least one replay from the new version locally:

```bash
python minimap_render_v2.py candidate_new_version_replay.wowsreplay
```

Check these visually:

- map size and alignment
- ship positions and spotting behavior
- shells, torpedoes, aircraft, smoke, radar, hydro, and consumable icons
- battle timer, score, and end result

### 8. Run Regression Tests

```bash
python -m unittest discover -s tests -q
```

If the tests pass and the sanity render looks correct, the render is ready for the new game version.

## Output Files

Depending on the command, the project can produce:

- rendered MP4 minimap videos
- canonical replay JSON
- legacy replay JSON
- entity analysis JSON
- battle statistics JSON
- comprehensive analysis JSON

## License

This project is licensed under the Apache License, Version 2.0.

Copyright 2026 Wargaming.net.

This project was developed at Wargaming.net's request for the community.
