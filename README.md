# HA Dashboard Player

A Home Assistant custom integration that exposes a virtual `media_player` entity and a Lovelace card for fullscreen dashboard playback. It is designed for HAOS kiosk usage on HDMI output using the HAOS Chromium Kiosk Addon https://github.com/speedy3wk/haos-chromium-kiosk.

## Features
- Media player entity with play, pause, stop, seek, volume, mute, repeat, shuffle.
- Displays images, video, and audio (audio uses black background).
- Optional media cache to `/config/www/ha-dashboard-player/cache` for HTTP/HTTPS sources.
- Restores last media on startup (optional).
- Card reports playback position/duration back to the entity when active.

## Installation

### HACS (Custom Repository)
1. Open HACS > Integrations.
2. Open the menu (top right) > Custom repositories.
3. Add `https://github.com/speedy3wk/ha-dashboard-player` with category `Integration`.
4. Find `HA Dashboard Player` in HACS and install.
5. Restart Home Assistant.
6. Add the integration via Settings > Devices & Services > Add Integration.

### Manual
1. Copy `custom_components/ha_dashboard_player` into your Home Assistant `custom_components` directory.
2. Copy `www/ha-dashboard-player/ha-dashboard-player.js` into your Home Assistant `www` directory.
3. Restart Home Assistant.
4. Add the integration via Settings > Devices & Services > Add Integration.

## Lovelace Resource
If you are not using HACS or prefer manual setup, add the frontend resource:

1. Settings > Dashboards > Resources > Add Resource
2. URL: `/local/ha-dashboard-player/ha-dashboard-player.js`
3. Resource type: `JavaScript Module`

## Lovelace Card
Add the card to a view:

```yaml
type: custom:ha-dashboard-player
entity: media_player.dashboard_player
show_controls: false
fit: contain
background: "#000000"
```

### Card Options
- `show_controls`: Show native audio/video controls (default `false`).
- `autoplay`: Autoplay media when possible (default `true`).
- `fullscreen`: Use fullscreen layout when in a panel view (default `false`).
- `kiosk_compat`: Force autoplay + muted for kiosk/WebKit usage (default `false`).
- `fit`: Media fit mode (`contain`, `cover`, `fill`).
- `background`: Background CSS color (default `#000000`).

The entity picker in the editor only lists HA Dashboard Player media players.

## Fullscreen Panel View
Create a panel view in your dashboard:

```yaml
title: Player
path: player
panel: true
cards:
  - type: custom:ha-dashboard-player
    entity: media_player.dashboard_player
    show_controls: false
```

## Services
- `media_player.play_media` to start playback. Use `media_content_type` values like `video`, `audio`, `music`, `image`.
- `ha_dashboard_player.preload_media` to cache a URL.
- `ha_dashboard_player.clear_screen` to show black screen.
- `ha_dashboard_player.report_state` is used by the Lovelace card to report playback position and duration (not for manual use).

## Notes
- HDMI audio output is handled by the HAOS host. Ensure the host audio output is set to HDMI.
- For local files, place media in `/media` or `/config/www` and reference via `media_source` or URL.
- Images report `media_duration=0` and ignore repeat/shuffle.
- Repeat is available for non-image media. Shuffle is only enabled for playlists.
- If the card is not active, playback position/duration is cleared after a short timeout.
- Created with AI-Tools, reviewed by me.
