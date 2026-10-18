# HA Dashboard Player

A Home Assistant custom integration that provides a virtual `media_player` entity and a Lovelace card for fullscreen playback on dashboards. It is built for HAOS kiosk screens on HDMI output with the [HAOS Chromium Kiosk App](https://github.com/speedy3wk/haos-chromium-kiosk), but works in any browser.

Play images, videos and audio from the Home Assistant **Media** panel, automations or scripts. The card on the screen renders the media and reports progress back to Home Assistant.

## Features
- `media_player` entity with play, pause, stop, seek, volume, mute and repeat.
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
- Shuffle was removed, because the player always plays a single item.
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

### Actions
| Action | Description |
| --- | --- |
| `ha_dashboard_player.preload_media` | Download a URL into the cache, so it plays instantly and offline later. Requires the cache option. |
| `ha_dashboard_player.clear_screen` | Stop and show the background only. |
| `ha_dashboard_player.report_state` | Used by the card to report playback; not meant for manual use. |

## Options
Change these under **Settings > Devices & services > HA Dashboard Player > Configure**:

- **Cache remote media:** HTTP(S) URLs are stored in `<local media folder>/ha_dashboard_player_cache` (on HAOS `/media/ha_dashboard_player_cache`). The first playback streams from the source and caches in the background; subsequent plays use the cached copy. The limits are 2 GiB per file and 10 GiB in total, and the oldest files are removed first.
- **Restore last media:** Resume the last media after a Home Assistant restart.

## Kiosk notes
- HDMI audio is handled by the HAOS host. Select HDMI as the host audio output.
- Enable hardware video decoding in the Chromium Kiosk App (`hw_video_decode`) for smooth high-resolution video on supported GPUs.
- When no screen reports for 15 seconds while playing, the media position is cleared, because it is unknown.

## Development

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt ruff
ruff check . && ruff format --check .
pytest
```

Created with AI tools, reviewed by me.
