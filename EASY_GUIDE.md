# Easy Guide

## What This Project Does

This project turns **World of Warships replay files** into a clean animated **minimap video**.

In simple terms:

- you give it a `.wowsreplay` file
- it reads the battle data
- it draws the ships, planes, smoke, caps, score, timer, and battle events
- it exports an MP4 video
- the Discord bot can do this for you with `/render` and `/render_dual`

It can also:

- compare two replays from the same battle side by side
- show battle overlays like smoke, radar, hydro, aircraft, and capture zones
- use ship and game data so names, icons, and ranges are more accurate

## What The Main Files Do

- `bot.py`
  Runs the Discord bot.
- `minimap_render_v2.py`
  Creates the MP4 video.
- `core/`
  Reads and extracts replay data.
- `renderers/`
  Draws the actual minimap video.
- `content/` and `gui/`
  Hold the game data and art assets the render needs.

## Normal Day-To-Day Use

### Discord

1. Start the bot.
2. Use `/render` for one replay.
3. Use `/render_dual` for two replays from the same battle.

### Local Render

```powershell
python .\minimap_render_v2.py .\your_replay.wowsreplay
```

## When You Need To Update The Project

You usually need to update the project after a **World of Warships patch** if:

- the render stops working on new replays
- ships or planes use wrong icons
- radar, hydro, smoke, or other consumables look wrong
- maps or capture areas look wrong
- the bot says the replay version is not supported

## Simple Update Workflow

Follow these steps in order.

### 1. Refresh The Game Data Used By The Project

Update the local game data and UI assets that this project depends on from the latest WoWS game client.

In plain language:

- copy in the fresh game data from the new game version
- make sure the project has the newest map, icon, and GameParams-related data

If you already have your own working routine for updating those files, keep using it.

### 2. Check The New Replay Version

Take:

- one replay from the **old working version**
- one replay from the **new game version**

Then run:

```powershell
python .\tools\update_wows_version.py old_replay.wowsreplay new_replay.wowsreplay --dump-render-packets
```

This helps the project compare the old replay format with the new one.

What to look for:

- whether it created a new version folder
- whether it says manual review is needed
- whether it wrote a report into `replay_debug/version_updates`

Important note:

- if the only warning is `strict replay player check failed`, do not panic
- open the generated `candidate_report.json`
- if `extract.ok` is `true` and `validation_ok` is `true`, the main render path is usually still fine
- in that case, the strict warning usually means the older replay-unpack helper hit a version quirk, not that the whole renderer is broken

### 3. Rebuild Aircraft Mapping

Run:

```powershell
python .\tools\rebuild_aircraft_params_from_gameparams.py
```

This refreshes plane type mapping so fighters, bombers, torpedo planes, ASW planes, and similar icons stay correct.

### 4. Refresh Radar And Hydro Data

Run:

```powershell
python .\tools\extract_gameparams_consumables.py --gameparams .\content\GameParams.data --out .\content\gameparams_consumables.json --keys PCY020_RLSSearchPremium PCY016_SonarSearchPremium
```

This refreshes important consumable values used by the render, especially:

- radar
- hydro

### 5. Refresh The Ship Cache

Run:

```powershell
python .\ships.py --update-cache
```

This updates the ship list and ship metadata cache.

### 6. Make A Test Render

Before using the new version in production, run a local test:

```powershell
python .\minimap_render_v2.py .\new_version_replay.wowsreplay
```

Check the result visually:

- map alignment
- ship positions
- smoke timing
- cap timing
- aircraft icons
- radar and hydro
- battle score and timer
- victory / defeat / draw result

### 7. Run The Tests

```powershell
python -m unittest discover -s tests -q
```

If the render looks correct and the tests pass, the update is normally good to go.

## Quick Checklist

If you want the short version:

1. Update the project's WoWS data/assets
2. Run `update_wows_version.py`
3. Run `rebuild_aircraft_params_from_gameparams.py`
4. Run `extract_gameparams_consumables.py`
5. Run `ships.py --update-cache`
6. Make a test render
7. Run the tests

## If Something Looks Wrong After Updating

If the render still looks wrong after a patch:

- wrong planes: rebuild aircraft params again
- wrong radar/hydro: rebuild consumable data again
- replay not decoding: check the version update report
- wrong map/caps/icons: re-check the copied game assets

## Good To Know

- The bot and the renderer do **not** update themselves automatically.
- The quality of the render depends on the game data being current.
- Most post-patch problems come from either:
  - replay version changes
  - outdated game data/assets
  - outdated aircraft or consumable extracts
