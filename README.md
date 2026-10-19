# HA Dashboard Player

A Home Assistant custom integration that provides a virtual `media_player` entity and a Lovelace card for fullscreen playback on dashboards. It is built for HAOS kiosk screens on HDMI output with the [HAOS Chromium Kiosk App](https://github.com/speedy3wk/haos-chromium-kiosk), but works in any browser.

Play images, videos and audio from the Home Assistant **Media** panel, automations or scripts. The card on the screen renders the media and reports progress back to Home Assistant.

## Features
- `media_player` entity with play, pause, stop, seek, volume, mute, repeat and shuffle.
- **Playlists** the Home Assistant way: queue items with `enqueue`, skip with next/previous, clear the playlist, and play whole media folders.
- Displays images, video and audio (audio is shown on the background color).
- **Media Source first:** browse and play everything from Settings > Media (local media, cameras, TTS, …). Media is resolved by the screen with short-lived signed URLs, so nothing has to be publicly reachable.
- Optional cache for remote HTTP(S) media in the authenticated local media folder.
- Optionally restores the last media after a restart.
- The card ships with the integration and is loaded automatically. You don't need to add a dashboard resource.
- Visual card editor that lists only HA Dashboard Player entities.

## Requirements
- Home Assistant **2026.10** or newer.

## Installation

### HACS (custom repository)
1. Open HACS, then the menu (top right) > **Custom repositories**.
2. Add `https://github.com/speedy3wk/ha-dashboard-player` with type **Integration**.
3. Install **HA Dashboard Player** and restart Home Assistant.
4. Go to **Settings > Devices & services > Add integration** and add **HA Dashboard Player** once per screen.

### Manual
1. Copy `custom_components/ha_dashboard_player` into your `custom_components` folder.
2. Restart Home Assistant and add the integration as described above.

## Upgrading from 0.1.x
Version 0.2.0 changed how the card is delivered and where media is cached:

1. Remove the old dashboard resource `/local/ha-dashboard-player/ha-dashboard-player.js` (**Settings > Dashboards > ⋮ > Resources**). The integration now loads the card itself, and a leftover resource would load an outdated card.
2. Delete the folder `/config/www/ha-dashboard-player` (including the old `cache`). Files under `/config/www` are publicly accessible without login. The new cache lives in the authenticated media folder.
3. Reload the browser on every screen (on the kiosk: restart the app).

Other changes:
- Entity names are no longer slugified. Version 0.1.x converted names to `snake_case`, based on a Home Assistant entity-ID rule that does not exist. Existing entity IDs are kept; new entries get the name exactly as entered.
- Shuffle was removed, because the player always plays a single item. Version 0.3.0 adds it back together with playlists.
- Restored media that was saved as an expiring signed URL is migrated to its media source ID automatically.

## Lovelace card
The card can be added with the visual editor (search for *HA Dashboard Player*) or in YAML:

```yaml
type: custom:ha-dashboard-player
entity: media_player.living_room
show_controls: false
fit: contain
background: "#000000"
```

| Option | Default | Description |
| --- | --- | --- |
| `entity` | – | The HA Dashboard Player entity. |
| `show_controls` | `false` | Show native audio/video controls. |
| `autoplay` | `true` | Start playback automatically. |
| `fit` | `contain` | `contain`, `cover` or `fill`. |
| `background` | `#000000` | Background CSS color. |
| `fullscreen` | `false` | Fill the viewport (use in a panel view). |
| `kiosk_compat` | `false` | Always play muted. Only needed for browsers that block autoplay with sound; the Chromium Kiosk App allows autoplay with sound. |
| `report_state` | `true` | Report playback progress to Home Assistant. Disable it on additional screens that show the same entity, so only one screen reports. |
| `debug` | `false` | Show a compact, read-only playback diagnostics overlay. Also available in the visual card editor. |

If a browser blocks autoplay with sound, the card automatically falls back to muted playback.

### Fullscreen panel view

```yaml
title: Player
path: player
panel: true
cards:
  - type: custom:ha-dashboard-player
    entity: media_player.living_room
    fullscreen: true
```

## Playing media

### From the Media panel
Open **Media**, choose the player in the lower right corner and pick a file.

### From automations and scripts

```yaml
action: media_player.play_media
target:
  entity_id: media_player.living_room
data:
  media_content_id: media-source://media_source/local/videos/welcome.mp4
  media_content_type: video
```

Supported `media_content_id` values:
- `media-source://…` IDs (recommended). Use the media browser in the action editor to pick them.
- `http(s)://…` URLs.
- Paths on your Home Assistant instance, such as `/local/picture.jpg` or `/api/…`. The screen signs them automatically when needed.

The media type is detected from the MIME type, `media_content_type` (`image`, `video`, `audio`/`music`) or the file extension.

### Playlists
The player keeps its own queue and uses the standard media player features, so the Media panel, the media control card, Music Assistant style automations and voice assistants work without extra configuration.

Add items with `enqueue`:

```yaml
action: media_player.play_media
target:
  entity_id: media_player.living_room
data:
  media_content_id: media-source://media_source/local/videos/news.mp4
  media_content_type: video
  enqueue: add  # replace (default), play, next or add
```

| `enqueue` | Effect |
| --- | --- |
| `replace` | Clear the queue and play the new item (default). |
| `play` | Insert after the current item and play it now. |
| `next` | Insert after the current item. |
| `add` | Append to the end. |

- **Folders:** pick a folder in the Media panel (or pass its `media-source://media_source/local/…` ID) to play all media files directly inside it in name order. Subfolders are not included.
- **Next / previous:** `media_player.media_next_track` and `media_player.media_previous_track`. Previous restarts the current item when it played for more than 3 seconds.
- **Repeat:** `off` stops after the last item, `all` loops the queue, `one` repeats the current item.
- **Shuffle:** `media_player.shuffle_set` shuffles the remaining items; turning it off restores the original order.
- **Clear:** `media_player.clear_playlist` removes all items except the current one. `media_stop` and `clear_screen` clear the whole queue.
- **Images** advance after the *image display duration* option (default 10 seconds). Pausing stops the slideshow.
- **Video and audio** advance when a screen reports the end of playback. At least one card with `report_state: true` must show the player; otherwise the queue stays on the current item.
- The attributes `queue_position` and `queue_size` show where the player is in the queue (max. 500 items). The queue is restored after a restart when *Restore last media* is enabled.

### Actions
| Action | Description |
| --- | --- |
| `ha_dashboard_player.preload_media` | Download a URL into the cache, so it plays instantly and offline later. Requires the cache option. |
| `ha_dashboard_player.clear_screen` | Stop and show the background only. |
| `ha_dashboard_player.report_state` | Used by the card to report playback; not meant for manual use. |
| `ha_dashboard_player.media_ended` | Used by the card to report the end of an item, so the playlist advances; not meant for manual use. |

## Options
Change these under **Settings > Devices & services > HA Dashboard Player > Configure**:

- **Cache remote media:** HTTP(S) URLs are stored in `<local media folder>/ha_dashboard_player_cache` (on HAOS `/media/ha_dashboard_player_cache`). The first playback streams from the source and caches in the background; subsequent plays use the cached copy. The limits are 2 GiB per file and 10 GiB in total, and the oldest files are removed first.
- **Restore last media:** Resume the last media and the playlist after a Home Assistant restart.
- **Image display duration:** Seconds each image is shown before a playlist advances (1–3600, default 10).

## Kiosk notes
- HDMI audio is handled by the HAOS host. Select HDMI as the host audio output.
- Enable hardware video decoding in the Chromium Kiosk App (`hw_video_decode`) for smooth high-resolution video on supported GPUs.
- When no screen reports for 15 seconds while playing, the media position is cleared, because it is unknown.

### Playback diagnostics

Enable **Show playback diagnostics** in the card settings (or set `debug: true` in YAML). No mouse or keyboard is needed on the playback screen. The overlay ignores pointer input and updates only its own text once per second, without rebuilding the player or sending additional reports to Home Assistant. Disabling it or removing the card stops the diagnostic timer.

The overlay shows:
- Card version, entity, HA state, reporting setting, page visibility and browser user agent.
- Playback time, duration, speed, buffered seconds ahead, ready/network state and media error code.
- Video resolution, displayed CSS size and device pixel ratio.
- Approximate non-dropped frames per second, total/dropped frames, drop percentage and drops since the previous sample, where the browser supports `getVideoPlaybackQuality()`. These are browser playback counters, not a measurement of HDMI refresh rate or proof of hardware decoding.
- `waiting`, `stalled` and `seeking` event counts, the last event, HA-triggered seek corrections and the last correction's signed time difference.
- Card state-update and source-load counts. Updates do not mean DOM rebuilds.

Event, correction, update and load counters start when diagnostics are enabled; frame counters refer to the browser's current media playback. The first frame-rate sample is unavailable until the next update. The overlay does not display media URLs or authentication tokens.

Rising dropped frames with a healthy buffer point toward a decoding/rendering bottleneck; an empty buffer and `waiting` events suggest media delivery cannot keep up. Increasing HA seek corrections indicate position synchronization is intervening. These are clues, not definitive diagnoses. Codec and active hardware-decoder details are not reliably exposed to web pages; use Chromium's `chrome://media-internals` for those.

The overlay itself can affect compositing and timing. Compare playback with diagnostics disabled as well.

## Development

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt ruff
ruff check . && ruff format --check .
pytest
node --test tests/frontend/*.test.mjs
```

Created with AI tools, reviewed by me.
