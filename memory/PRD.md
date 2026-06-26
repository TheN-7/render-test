# WoWS Replay Minimap Renderer — PRD / Change Log

## Project
CLI/library tool that parses World of Warships `.wowsreplay` files and renders an
animated minimap MP4 (`minimap_render_v2.py` -> `renderers/minimap_renderer.py`).
No web frontend/backend; runs as Python scripts / Discord bot.

## Problem addressed (2026-06-26)
Ally ships disappeared from the render the moment they left the player's spotting
range (e.g. Napoli, Småland), even though their shells/smoke stayed and the in-game
minimap keeps showing allies moving. Requirement: keep ALLY ships visible out of
spotting range like the WoWS minimap — shown as a faded/hollow "last-known" marker,
keeping the ship name + HP bar + heading. Enemies unchanged.

## Root cause
The replay already contains the WoWS minimap-vision channel
(`Avatar_updateMinimapVisionInfo` -> `meta.minimap_vision_timeline`), decoded by the
renderer. But the decoded vision points were only used for ships that had NO real
track at all; the helper `_merge_friendly_track_with_vision` was defined but never
called. Allies with a real track that stopped (out of range) kept their frozen track,
were flagged "stale", and `continue`d (hidden) in `iter_animation_frames`.
Additionally the 10-bit packed Z axis wrapped (~1024 levels) and the unwrap was only
applied to X, so vision tracks got truncated by the out-of-bounds sanitizer.

## Changes (renderers/minimap_renderer.py)
1. `_merge_friendly_track_with_vision`: tag inserted vision points with `"vision": True`.
2. `_unwrap_vision_points_continuity` (new) applied in `_minimap_vision_tracks`:
   continuity-unwraps both packed axes so vision tracks no longer truncate on wrap.
3. `_normalize_render_tracks`: merge decoded minimap-vision points into ALLY tracks
   that already have a real track (fills the post-spotting gap); set
   `has_minimap_vision`; tag vision-only ally tracks.
4. `_prepare_track_render_data`: expose `real_times` (timestamps of real position
   packets only, excluding vision-fill points).
5. `iter_animation_frames`: `actively_spotted` is now decided by real packets only.
   Out-of-range allies that are still known via minimap-vision are drawn as a faded/
   hollow marker (keeping name, HP bar, heading) instead of being hidden. Enemies are
   unchanged (still disappear when lost).

## Verification
- Extracted the user's replay (Hawaii / tierra_del_fuego). Ally Napoli real track ends
  at t=248.9s, battle ends 662.6s; minimap-vision covers it to 655.5s (dies at 657).
- After fix: Napoli merged track spans 0→655s, all within world bounds.
- Rendered frames at t=250/400/600 + full MP4: out-of-range Napoli shows as a hollow
  faded green icon with name label, HP bar and movement heading (visually confirmed).
- Full MP4 pipeline + render_static run clean. Test suite: the 7 failing tests fail
  identically WITHOUT these changes (pre-existing, missing map/icon assets in this env).

## Follow-up tweaks (2026-06-26)
- Out-of-range allies keep their NORMAL solid icon (no hollow/pixelated "stale"
  style). In `iter_animation_frames`, out-of-range allies are drawn with
  `draw_stale=False` so the icon never changes when leaving spotting range.
- Heading fix: minimap-vision points have no yaw, so merged points inherited the
  last spotted yaw. When an ally maneuvered out of range it faced backwards and
  snapped 180 deg on re-spot (observed on Småland t~379-446s, all vision points).
  Now out-of-range allies (`friendly_out_of_range`) are oriented by their actual
  direction of travel (`_movement_heading_metrics`, window=5, lerp 0.6). Verified:
  resolved heading tracks travel direction within avg ~14 deg (was 110-167 deg /
  reversed); icon nose points forward along the trail.

## Data audit (2026-06-26, tierra_del_fuego replay, client 15.5.0)
Audited canonical data vs renderer usage. Findings:
- HIGH: radar/hydro sensor rings absent. In v15.5 the consumable-used payload is an
  opaque pickled blob (unpickle fails) and `setConsumables` carries no readable name
  tokens, so kind is recovered only by duration-matching reference data. heal/smoke/
  engine/dcp/dfaa/reload_booster recover; radar/hydro activations are not observed in
  the consumable stream at all (4+ radar ships present). Needs dedicated v15.5
  consumable-packet reverse engineering. Applied a safe partial fix: radar token
  matcher now also recognizes "rls"/"rlssearch" (WoWS internal name) — helps when
  names are present but does NOT resolve the opaque-payload case in this replay.
- LOW: artillery `shell_kind` is empty for all 1740 shots (diagnostics
  shell_kinds_resolved=0), so HE/AP/CS tracer + kill-feed coloring falls back to
  default white. `battery_kind` (main/secondary) does resolve.
- LOW: ally Napoli has one ~12s minimap-vision gap (~t=491) where the icon holds its
  last position before resuming; all other allies have <2.5s gaps.
- INFO: events.spotting and events.sensors are empty; chat (6) and weatherParams are
  parsed but intentionally not rendered; secondary artillery tracers (1111) are drawn.

## Next / Backlog
- P2: Optionally add a "last seen Xs ago" hint near faded ally markers.
- P2: Consider applying the same faded treatment in the final static summary PNG.
- P3: The 7 pre-existing test failures need the full WoWS content assets to pass.
