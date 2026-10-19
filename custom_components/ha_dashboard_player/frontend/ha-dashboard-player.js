/* HA Dashboard Player card */

const CARD_VERSION = "0.2.1";
const INTEGRATION = "ha_dashboard_player";
const MEDIA_SOURCE_PREFIX = "media-source://";
const SIGNED_URL_EXPIRES = 24 * 60 * 60;
const HEARTBEAT_MS = 5000;
const SEEK_TOLERANCE_S = 1.5;

const DEFAULT_CONFIG = {
  show_controls: false,
  autoplay: true,
  fit: "contain",
  background: "#000000",
  fullscreen: false,
  kiosk_compat: false,
  report_state: true,
  debug: false,
};

const LOCALIZATION = {
  en: {
    entity: "Entity",
    show_controls: "Show controls",
    autoplay: "Autoplay",
    fullscreen: "Fullscreen (panel view)",
    kiosk_compat: "Always muted (for browsers that block autoplay with sound)",
    report_state: "Report playback to Home Assistant",
    report_state_helper:
      "Disable on secondary screens that show the same player.",
    debug: "Show playback diagnostics",
    debug_helper: "Read-only overlay for diagnosing playback on kiosk screens.",
    debug_idle: "No active media",
    debug_decoder: "HW decoder / codec: not exposed by the browser",
    fit: "Fit",
    background: "Background (CSS color)",
  },
  de: {
    entity: "Entität",
    show_controls: "Steuerung anzeigen",
    autoplay: "Autoplay",
    fullscreen: "Vollbild (Panel-Ansicht)",
    kiosk_compat: "Immer stumm (für Browser, die Autoplay mit Ton blockieren)",
    report_state: "Wiedergabe an Home Assistant melden",
    report_state_helper:
      "Auf weiteren Bildschirmen mit demselben Player deaktivieren.",
    debug: "Wiedergabe-Diagnose anzeigen",
    debug_helper: "Nur lesbare Diagnose-Anzeige zur Fehlersuche auf Kiosk-Bildschirmen.",
    debug_idle: "Keine aktiven Medien",
    debug_decoder: "HW-Decoder / Codec: vom Browser nicht offengelegt",
    fit: "Anpassen",
    background: "Hintergrund (CSS-Farbe)",
  },
};

const localize = (key, language) => {
  const lang = (language || navigator.language || "en").split("-")[0];
  return (LOCALIZATION[lang] || LOCALIZATION.en)[key] || LOCALIZATION.en[key];
};

const isDashboardPlayer = (hass, entityId) =>
  Boolean(hass?.states?.[entityId]?.attributes?.[INTEGRATION]);

const mediaKind = (attrs) => {
  if (["image", "video", "audio"].includes(attrs.media_kind)) {
    return attrs.media_kind;
  }
  const type = String(attrs.media_content_type || "").toLowerCase();
  if (type.startsWith("image")) return "image";
  if (type.startsWith("audio") || type === "music") return "audio";
  return "video";
};

const TEMPLATE = document.createElement("template");
TEMPLATE.innerHTML = `
  <style>
    :host {
      display: block;
      height: 100%;
      min-height: 100%;
      background: var(--ha-dashboard-player-bg, #000000);
    }
    :host(.fullscreen) {
      width: 100vw;
      height: 100vh;
      min-height: 100vh;
    }
    .surface {
      position: relative;
      width: 100%;
      height: 100%;
      min-height: inherit;
      overflow: hidden;
      background: var(--ha-dashboard-player-bg, #000000);
    }
    video,
    audio,
    img {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      background: var(--ha-dashboard-player-bg, #000000);
    }
    video,
    img {
      object-fit: var(--ha-dashboard-player-fit, contain);
    }
    .debug {
      position: absolute;
      top: 8px;
      left: 8px;
      z-index: 1;
      box-sizing: border-box;
      max-width: calc(100% - 16px);
      max-height: calc(100% - 16px);
      overflow: hidden;
      margin: 0;
      padding: 8px 10px;
      color: #fff;
      background: rgba(0, 0, 0, 0.8);
      font: 12px/1.4 monospace;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      pointer-events: none;
      user-select: none;
    }
    .hidden {
      display: none;
    }
  </style>
  <div class="surface">
    <video class="hidden" playsinline></video>
    <audio class="hidden"></audio>
    <img class="hidden" alt="" />
    <pre class="debug hidden" aria-hidden="true"></pre>
  </div>
`;

class HADashboardPlayerCard extends HTMLElement {
  constructor() {
    super();
    this._config = null;
    this._hass = null;
    this._stateObj = null;
    this._active = null; // { kind, source, url, element }
    this._renderToken = 0;
    this._lastReport = null;
    this._lastHeartbeat = 0;
    this._retriedSource = null;
    this._suppressEvents = false;
    this._autoMuted = false;
    this._resolved = new Map();
    this._debug = null;
    this._debugTimer = null;
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: {
            entity: {
              filter: { domain: "media_player", integration: INTEGRATION },
            },
          },
        },
        {
          name: "fit",
          selector: {
            select: {
              mode: "dropdown",
              options: ["contain", "cover", "fill"],
            },
          },
        },
        { name: "background", selector: { text: {} } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "show_controls", selector: { boolean: {} } },
            { name: "autoplay", selector: { boolean: {} } },
            { name: "fullscreen", selector: { boolean: {} } },
            { name: "kiosk_compat", selector: { boolean: {} } },
            { name: "report_state", selector: { boolean: {} } },
            { name: "debug", selector: { boolean: {} } },
          ],
        },
      ],
      computeLabel: (schema) =>
        localize(schema.name, document.querySelector("home-assistant")?.hass?.language),
      computeHelper: (schema) =>
        ["report_state", "debug"].includes(schema.name)
          ? localize(
              `${schema.name}_helper`,
              document.querySelector("home-assistant")?.hass?.language
            )
          : undefined,
    };
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (entityId) =>
        entityId.startsWith("media_player.") && isDashboardPlayer(hass, entityId)
    );
    return {
      type: "custom:ha-dashboard-player",
      entity: entity || "",
    };
  }

  setConfig(config) {
    if (!config?.entity) {
      throw new Error("Entity is required");
    }
    this._config = { ...DEFAULT_CONFIG, ...config };

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.appendChild(TEMPLATE.content.cloneNode(true));
      this._elements = {
        video: this.shadowRoot.querySelector("video"),
        audio: this.shadowRoot.querySelector("audio"),
        image: this.shadowRoot.querySelector("img"),
      };
      this._debugElement = this.shadowRoot.querySelector(".debug");
      this._bindEvents();
    }

    this._applyConfig();
    this._stateObj = this._hass?.states[this._config.entity];
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const stateObj = this._config ? hass.states[this._config.entity] : undefined;
    // `hass` changes on every state change in Home Assistant; only react to ours.
    if (stateObj === this._stateObj) {
      return;
    }
    // A live update arrives right after the server wrote it, so its
    // last_updated can stand in for the server clock (avoids clock skew).
    const live = Boolean(this._stateObj && stateObj);
    this._stateObj = stateObj;
    this._render(live);
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, rows: 6, min_columns: 6, min_rows: 3 };
  }

  disconnectedCallback() {
    this._stopDebugTimer();
    this._unload();
  }

  connectedCallback() {
    this._syncDebug();
    if (this._config && this._hass) {
      this._stateObj = null;
      this.hass = this._hass;
    }
  }

  _applyConfig() {
    this.classList.toggle("fullscreen", Boolean(this._config.fullscreen));
    this.style.setProperty("--ha-dashboard-player-bg", this._config.background);
    this.style.setProperty("--ha-dashboard-player-fit", this._config.fit);
    for (const element of [this._elements.video, this._elements.audio]) {
      element.controls = Boolean(this._config.show_controls);
      element.autoplay = Boolean(this._config.autoplay);
      element.preload = "auto";
    }
    this._syncDebug();
  }

  _stopDebugTimer() {
    if (this._debugTimer !== null) {
      clearInterval(this._debugTimer);
      this._debugTimer = null;
    }
    if (this._debug) this._debug.sample = null;
  }

  _syncDebug() {
    if (!this._debugElement) return;
    const enabled = Boolean(this._config?.debug);
    this._debugElement.classList.toggle("hidden", !enabled);
    if (!enabled) {
      this._stopDebugTimer();
      this._debug = null;
      this._debugElement.textContent = "";
      return;
    }
    this._debug ||= {
      renders: 0,
      loads: 0,
      waiting: 0,
      stalled: 0,
      seeking: 0,
      corrections: 0,
      lastCorrection: null,
      lastEvent: "-",
      sample: null,
    };
    this._updateDebug();
    if (this.isConnected && this._debugTimer === null) {
      this._debugTimer = setInterval(() => this._updateDebug(), 1000);
    }
  }

  _updateDebug() {
    if (!this._debug || !this._debugElement) return;
    const debug = this._debug;
    const language = this._hass?.language;
    const lines = [
      `HA Dashboard Player ${CARD_VERSION} | ${this._config.entity}`,
      `HA: ${this._stateObj?.state || "-"} | reports: ${Boolean(this._config.report_state)} | visibility: ${document.visibilityState}`,
    ];
    const active = this._active;
    const number = (value) => Number.isFinite(value) ? value.toFixed(1) : "-";
    if (active && active.kind !== "image") {
      const element = active.element;
      const ready = ["nothing", "metadata", "current", "future", "enough"];
      const network = ["empty", "idle", "loading", "no source"];
      let buffered = 0;
      for (let i = 0; i < element.buffered.length; i++) {
        if (
          element.buffered.start(i) <= element.currentTime &&
          element.currentTime <= element.buffered.end(i)
        ) {
          buffered = element.buffered.end(i) - element.currentTime;
          break;
        }
      }
      lines.push(
        `${active.kind}: ${element.paused ? "paused" : "playing"} | seeking: ${element.seeking} | ended: ${element.ended}`,
        `time: ${number(element.currentTime)} / ${number(element.duration)} s | rate: ${element.playbackRate}x | buffer: ${number(buffered)} s`,
        `ready: ${ready[element.readyState] ?? "-"} | network: ${network[element.networkState] ?? "-"} | error: ${element.error?.code ?? "-"}`,
      );
      if (active.kind === "video") {
        const rect = element.getBoundingClientRect();
        lines.push(
          `video: ${element.videoWidth}x${element.videoHeight} | CSS: ${Math.round(rect.width)}x${Math.round(rect.height)} | DPR: ${window.devicePixelRatio}`,
        );
        const quality = element.getVideoPlaybackQuality?.();
        if (quality) {
          const now = performance.now();
          const total = quality.totalVideoFrames;
          const dropped = quality.droppedVideoFrames;
          const previous = debug.sample;
          let fps = "-";
          let recentDrops = "-";
          if (
            previous &&
            now > previous.time &&
            total >= previous.total &&
            dropped >= previous.dropped
          ) {
            const displayed = (total - dropped) - (previous.total - previous.dropped);
            fps = number(Math.max(0, displayed) * 1000 / (now - previous.time));
            recentDrops = String(dropped - previous.dropped);
          }
          debug.sample = { time: now, total, dropped };
          lines.push(
            `frames/s: ${fps} | frames: ${total} | dropped: ${dropped} (${number(total ? dropped * 100 / total : 0)}%) | drops/interval: ${recentDrops}`,
          );
        } else {
          lines.push("frames/s / dropped: n/a (API)");
        }
        lines.push(localize("debug_decoder", language));
      }
    } else {
      lines.push(active?.kind || localize("debug_idle", language));
    }
    lines.push(
      `events: waiting ${debug.waiting} | stalled ${debug.stalled} | seeking ${debug.seeking} | last: ${debug.lastEvent}`,
      `HA seek corrections: ${debug.corrections} | last delta: ${number(debug.lastCorrection)} s`,
      `updates: ${debug.renders} | source loads: ${debug.loads}`,
      navigator.userAgent,
    );
    const text = lines.join("\n");
    if (this._debugElement.textContent !== text) {
      this._debugElement.textContent = text;
    }
  }

  _bindEvents() {
    for (const element of [this._elements.video, this._elements.audio]) {
      for (const type of ["waiting", "stalled", "seeking", "seeked", "playing", "pause", "ended", "error"]) {
        element.addEventListener(type, () => {
          if (!this._debug || this._active?.element !== element) return;
          this._debug.lastEvent = type;
          if (["waiting", "stalled", "seeking"].includes(type)) {
            this._debug[type]++;
          }
        });
      }
      element.addEventListener("play", (ev) => this._onPlaybackEvent(ev, "playing"));
      element.addEventListener("pause", (ev) => this._onPause(ev));
      element.addEventListener("timeupdate", (ev) => this._onTimeUpdate(ev));
      for (const type of ["seeked", "loadedmetadata"]) {
        element.addEventListener(type, (ev) => this._onPlaybackEvent(ev, null, true));
      }
      for (const type of ["durationchange", "volumechange"]) {
        element.addEventListener(type, (ev) => this._onPlaybackEvent(ev, null));
      }
      element.addEventListener("ended", (ev) => this._onEnded(ev));
      element.addEventListener("error", (ev) => this._onError(ev));
      element.addEventListener("loadeddata", (ev) => this._onLoaded(ev));
    }
    this._elements.image.addEventListener("error", (ev) => this._onError(ev));
    this._elements.image.addEventListener("load", (ev) => this._onLoaded(ev));
  }

  async _render(live = false) {
    if (!this._config || !this._hass || !this._elements) {
      return;
    }
    if (this._debug) this._debug.renders++;
    const token = ++this._renderToken;
    const stateObj = this._stateObj;
    const attrs = stateObj?.attributes || {};
    const state = stateObj?.state;
    const source = attrs.media_url || attrs.media_content_id;

    if (
      !source ||
      !["playing", "paused"].includes(state) ||
      (mediaKind(attrs) === "image" && state !== "playing")
    ) {
      this._unload();
      return;
    }

    const kind = mediaKind(attrs);
    if (
      !this._active ||
      this._active.source !== source ||
      this._active.kind !== kind ||
      this._active.failed
    ) {
      const retry = Boolean(this._active?.failed);
      let url;
      try {
        url = await this._resolveUrl(source, retry);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("ha-dashboard-player: unable to resolve", source, err);
        if (token === this._renderToken) this._unload();
        return;
      }
      if (token !== this._renderToken) {
        return;
      }
      this._load(kind, source, url);
    }

    if (kind !== "image") {
      this._applyPlayback(this._active.element, state, attrs, live && stateObj.last_updated);
    }
  }

  async _resolveUrl(source, force = false) {
    const needsResolve =
      source.startsWith(MEDIA_SOURCE_PREFIX) ||
      (source.startsWith("/") &&
        !source.startsWith("/local/") &&
        !source.includes("authSig="));
    if (!needsResolve) {
      return source;
    }
    const cached = this._resolved.get(source);
    if (!force && cached && cached.expires > Date.now()) {
      return cached.url;
    }
    const result = source.startsWith(MEDIA_SOURCE_PREFIX)
      ? await this._hass.callWS({
          type: "media_source/resolve_media",
          media_content_id: source,
          expires: SIGNED_URL_EXPIRES,
        })
      : await this._hass.callWS({
          type: "auth/sign_path",
          path: source,
          expires: SIGNED_URL_EXPIRES,
        });
    const url = result.url || result.path;
    // Refresh well before the signature expires.
    this._resolved.set(source, {
      url,
      expires: Date.now() + (SIGNED_URL_EXPIRES * 1000) / 2,
    });
    return url;
  }

  _load(kind, source, url) {
    const element = kind === "image" ? this._elements.image
      : kind === "audio" ? this._elements.audio
      : this._elements.video;

    this._unload(element);
    this._active = { kind, source, url, element };
    if (this._debug) {
      this._debug.loads++;
      this._debug.sample = null;
      this._debug.lastEvent = "load";
    }
    this._lastReport = null;
    this._autoMuted = false;
    this._retriedSource = this._retriedSource === source ? source : null;
    element.setAttribute("src", url);
    element.classList.remove("hidden");
  }

  _unload(except = null) {
    this._suppressEvents = true;
    try {
      for (const element of Object.values(this._elements || {})) {
        if (element === except) continue;
        element.classList.add("hidden");
        if (!element.hasAttribute("src")) continue;
        if (element.pause) element.pause();
        element.removeAttribute("src");
        if (element.load) element.load();
      }
    } finally {
      this._suppressEvents = false;
    }
    if (!except) {
      this._active = null;
    }
  }

  _applyPlayback(element, state, attrs, serverNow) {
    this._suppressEvents = true;
    try {
      element.muted = Boolean(
        this._config.kiosk_compat || this._autoMuted || attrs.is_volume_muted
      );
      if (typeof attrs.volume_level === "number") {
        element.volume = Math.min(1, Math.max(0, attrs.volume_level));
      }
      element.loop = attrs.repeat === "one" || attrs.repeat === "all";

      const position = this._targetPosition(state, attrs, serverNow);
      if (
        position !== null &&
        element.readyState >= 1 &&
        Math.abs(element.currentTime - position) > SEEK_TOLERANCE_S
      ) {
        if (this._debug) {
          this._debug.corrections++;
          this._debug.lastCorrection = position - element.currentTime;
        }
        element.currentTime = position;
      }
    } finally {
      this._suppressEvents = false;
    }

    if (state === "playing" && element.paused) {
      element.play().catch((err) => this._onPlayRejected(element, err));
    } else if (state === "paused" && !element.paused) {
      element.pause();
    }
  }

  _onPlayRejected(element, err) {
    if (err?.name !== "NotAllowedError" || element.muted) {
      return;
    }
    // Browser autoplay policy: fall back to muted playback.
    // eslint-disable-next-line no-console
    console.info("ha-dashboard-player: autoplay with sound blocked, playing muted");
    this._autoMuted = true;
    element.muted = true;
    element.play().catch(() => undefined);
  }

  _targetPosition(state, attrs, serverNow) {
    if (typeof attrs.media_position !== "number") {
      return null;
    }
    let position = attrs.media_position;
    if (state === "playing" && attrs.media_position_updated_at) {
      const updated = Date.parse(attrs.media_position_updated_at);
      const now = serverNow ? Date.parse(serverNow) : Date.now();
      if (!Number.isNaN(updated) && !Number.isNaN(now)) {
        position += Math.max(0, (now - updated) / 1000);
      }
    }
    return position;
  }

  _isActiveEvent(event) {
    return (
      !this._suppressEvents &&
      this._active &&
      event?.target === this._active.element &&
      event.target.readyState >= 1
    );
  }

  _onPlaybackEvent(event, state, force = false) {
    if (this._isActiveEvent(event)) {
      this._report(event.target, state, force);
    }
  }

  _onPause(event) {
    // A pause right before "ended" is not a user pause.
    if (this._isActiveEvent(event) && !event.target.ended) {
      this._report(event.target, "paused");
    }
  }

  _onTimeUpdate(event) {
    if (!this._isActiveEvent(event)) {
      return;
    }
    const now = Date.now();
    if (now - this._lastHeartbeat < HEARTBEAT_MS) {
      return;
    }
    this._lastHeartbeat = now;
    this._report(event.target, null, true);
  }

  _onEnded(event) {
    if (!this._active || event?.target !== this._active.element || event.target.loop) {
      return;
    }
    if (this._shouldReport()) {
      this._hass.callService("media_player", "media_stop", {
        entity_id: this._config.entity,
      });
    }
  }

  _onLoaded(event) {
    if (this._active && event?.target === this._active.element) {
      this._retriedSource = null;
    }
  }

  async _onError(event) {
    if (!this._active || event?.target !== this._active.element) {
      return;
    }
    const { source, kind } = this._active;
    // eslint-disable-next-line no-console
    console.warn("ha-dashboard-player: failed to load", source);
    if (this._retriedSource === source) {
      // Reload on the next state change, e.g. when play_media is called again.
      this._active.failed = true;
      return;
    }
    // Signed URLs expire; resolve once more before giving up.
    this._retriedSource = source;
    try {
      const url = await this._resolveUrl(source, true);
      if (this._active?.source === source) {
        this._load(kind, source, url);
        this._retriedSource = source;
        this._stateObj = null;
        this.hass = this._hass;
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("ha-dashboard-player: re-resolve failed", err);
      if (this._active?.source === source) this._active.failed = true;
    }
  }

  _shouldReport() {
    return (
      this._config?.report_state !== false &&
      this._hass &&
      document.visibilityState !== "hidden"
    );
  }

  _report(element, state, force = false) {
    if (!this._shouldReport()) {
      return;
    }
    const payload = { entity_id: this._config.entity };
    if (state) payload.state = state;
    if (Number.isFinite(element.currentTime) && element.currentTime >= 0) {
      payload.media_position = Math.round(element.currentTime * 10) / 10;
    }
    if (Number.isFinite(element.duration) && element.duration >= 0) {
      payload.media_duration = Math.round(element.duration * 10) / 10;
    }
    if (Number.isFinite(element.volume)) {
      payload.volume_level = Math.round(element.volume * 100) / 100;
    }
    if (!this._config.kiosk_compat && !this._autoMuted) {
      payload.is_volume_muted = element.muted;
    }

    const key = JSON.stringify({ ...payload, media_position: undefined });
    if (!force && !state && this._lastReport === key) {
      return;
    }
    this._lastReport = key;
    this._hass
      .callService(INTEGRATION, "report_state", payload)
      .catch((err) =>
        // eslint-disable-next-line no-console
        console.debug("ha-dashboard-player: report_state failed", err)
      );
  }
}

if (!customElements.get("ha-dashboard-player")) {
  customElements.define("ha-dashboard-player", HADashboardPlayerCard);
  // eslint-disable-next-line no-console
  console.info(`%c HA-DASHBOARD-PLAYER %c v${CARD_VERSION} `,
    "color: white; background: #03a9f4; font-weight: 700;",
    "color: #03a9f4; background: white; font-weight: 700;");
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "ha-dashboard-player")) {
  window.customCards.push({
    type: "ha-dashboard-player",
    name: "HA Dashboard Player",
    description: "Fullscreen media player for dashboards and kiosk screens.",
    preview: false,
    documentationURL: "https://github.com/speedy3wk/ha-dashboard-player",
    getEntitySuggestion: (hass, entityId) =>
      isDashboardPlayer(hass, entityId)
        ? { config: { type: "custom:ha-dashboard-player", entity: entityId } }
        : null,
  });
}
