/* HA Dashboard Player card */

const DEFAULT_CONFIG = {
  show_controls: false,
  autoplay: true,
  fit: "contain",
  background: "#000000",
  fullscreen: false,
  kiosk_compat: false,
};

const LOCALIZATION = {
  en: {
    entity: "Entity",
    show_controls: "Show controls",
    autoplay: "Autoplay",
    fullscreen: "Fullscreen (panel)",
    kiosk_compat: "Kiosk compat (WebKit)",
    fit: "Fit (contain | cover | fill)",
    background: "Background (CSS color)",
  },
  de: {
    entity: "Entitaet",
    show_controls: "Steuerung anzeigen",
    autoplay: "Autoplay",
    fullscreen: "Vollbild (Panel)",
    kiosk_compat: "Kiosk-kompatibel (WebKit)",
    fit: "Anpassen (contain | cover | fill)",
    background: "Hintergrund (CSS-Farbe)",
  },
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

    .player {
      width: 100%;
      height: 100%;
      background: var(--ha-dashboard-player-bg, #000000);
    }

    .surface {
      position: relative;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: var(--ha-dashboard-player-bg, #000000);
    }

    video,
    audio,
    img,
    .idle {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
    }

    video,
    img {
      object-fit: var(--ha-dashboard-player-fit, contain);
      background: var(--ha-dashboard-player-bg, #000000);
    }

    audio {
      background: var(--ha-dashboard-player-bg, #000000);
    }

    .hidden {
      display: none;
    }

    .idle {
      background: var(--ha-dashboard-player-bg, #000000);
    }
  </style>
  <div class="player">
    <div class="surface">
      <video class="hidden" playsinline></video>
      <audio class="hidden"></audio>
      <img class="hidden" alt="" />
      <div class="idle"></div>
    </div>
  </div>
`;

class HADashboardPlayerCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("ha-dashboard-player-editor");
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (key) => hass.states[key].entity_id?.startsWith("media_player.")
    );
    return {
      type: "custom:ha-dashboard-player",
      entity: entity || "media_player.dashboard_player",
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._updateFromState();
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Entity is required");
    }

    this._config = { ...DEFAULT_CONFIG, ...config };

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.appendChild(TEMPLATE.content.cloneNode(true));
      this._video = this.shadowRoot.querySelector("video");
      this._audio = this.shadowRoot.querySelector("audio");
      this._img = this.shadowRoot.querySelector("img");
      this._idle = this.shadowRoot.querySelector(".idle");
      this._onMediaEnded = (event) => this._handleMediaEnded(event);
      this._onMediaPlay = (event) => this._handleMediaPlay(event);
      this._onMediaPause = (event) => this._handleMediaPause(event);
      this._onMediaTimeUpdate = (event) => this._handleMediaTimeUpdate(event);
      this._onMediaSeeked = (event) => this._handleMediaSeeked(event);
      this._onMediaLoaded = (event) => this._handleMediaLoaded(event);
      this._onMediaDuration = (event) => this._handleMediaDuration(event);
      this._onMediaVolume = (event) => this._handleMediaVolume(event);
      this._lastReportPayload = null;
      this._entityState = null;
      this._reportedImageUrl = null;
      this._lastMediaTime = null;
      this._lastPositionReport = 0;

      this._video.addEventListener("ended", this._onMediaEnded);
      this._audio.addEventListener("ended", this._onMediaEnded);
      this._video.addEventListener("play", this._onMediaPlay);
      this._audio.addEventListener("play", this._onMediaPlay);
      this._video.addEventListener("pause", this._onMediaPause);
      this._audio.addEventListener("pause", this._onMediaPause);
      this._video.addEventListener("timeupdate", this._onMediaTimeUpdate);
      this._audio.addEventListener("timeupdate", this._onMediaTimeUpdate);
      this._video.addEventListener("seeked", this._onMediaSeeked);
      this._audio.addEventListener("seeked", this._onMediaSeeked);
      this._video.addEventListener("loadedmetadata", this._onMediaLoaded);
      this._audio.addEventListener("loadedmetadata", this._onMediaLoaded);
      this._video.addEventListener("durationchange", this._onMediaDuration);
      this._audio.addEventListener("durationchange", this._onMediaDuration);
      this._video.addEventListener("volumechange", this._onMediaVolume);
      this._audio.addEventListener("volumechange", this._onMediaVolume);
    }

    this._applyConfig();
  }

  getCardSize() {
    return 3;
  }

  _applyConfig() {
    if (!this.shadowRoot) {
      return;
    }

    this.classList.toggle("fullscreen", Boolean(this._config.fullscreen));
    this.style.setProperty("--ha-dashboard-player-bg", this._config.background);
    this.style.setProperty("--ha-dashboard-player-fit", this._config.fit);

    const controls = Boolean(this._config.show_controls);
    this._video.controls = controls;
    this._audio.controls = controls;

    const kioskCompat = Boolean(this._config.kiosk_compat);
    const autoplay = Boolean(this._config.autoplay) || kioskCompat;
    this._video.autoplay = autoplay;
    this._audio.autoplay = autoplay;
    this._video.preload = kioskCompat ? "auto" : "metadata";
    this._audio.preload = kioskCompat ? "auto" : "metadata";
    if (kioskCompat) {
      this._video.muted = true;
      this._audio.muted = true;
    }
  }

  _updateFromState() {
    if (!this._hass || !this._config) {
      return;
    }

    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj) {
      this._entityState = null;
      this._reportedImageUrl = null;
      this._setIdle();
      return;
    }

    const attrs = stateObj.attributes || {};
    const state = stateObj.state;
    this._entityState = state;
    const mediaUrl = attrs.media_url || attrs.entity_picture || attrs.media_content_id;
    const mediaType = attrs.media_content_type || "";

    if (!mediaUrl || state === "idle" || state === "off") {
      this._reportedImageUrl = null;
      this._setIdle();
      return;
    }

    if (mediaType.startsWith("image")) {
      if (state !== "playing") {
        this._reportedImageUrl = null;
        this._setIdle();
        return;
      }
      this._showImage(mediaUrl);
      return;
    }

    if (mediaType.startsWith("video")) {
      this._showVideo(mediaUrl, state, attrs);
      return;
    }

    if (mediaType.startsWith("audio") || mediaType === "music") {
      this._showAudio(mediaUrl, state, attrs);
      return;
    }

    this._setIdle();
  }

  _setIdle() {
    this._hideAll();
    this._idle.classList.remove("hidden");
    if (this._video) {
      this._video.pause();
      this._video.removeAttribute("src");
      this._video.load();
    }
    if (this._audio) {
      this._audio.pause();
      this._audio.removeAttribute("src");
      this._audio.load();
    }
  }

  _hideAll() {
    this._video.classList.add("hidden");
    this._audio.classList.add("hidden");
    this._img.classList.add("hidden");
    this._idle.classList.add("hidden");
  }

  _showImage(url) {
    this._hideAll();
    this._img.src = url;
    this._img.classList.remove("hidden");
    if (this._reportedImageUrl !== url) {
      this._reportedImageUrl = url;
      this._reportState("playing", 0, 0, null, null, null, null, true);
    }
  }

  _showVideo(url, state, attrs) {
    this._hideAll();
    const currentSrc = this._video.getAttribute("src");
    if (currentSrc !== url) {
      this._video.setAttribute("src", url);
      this._lastMediaTime = null;
    }
    this._applyMediaSettings(this._video, state, attrs);
    this._video.classList.remove("hidden");
  }

  _showAudio(url, state, attrs) {
    this._hideAll();
    const currentSrc = this._audio.getAttribute("src");
    if (currentSrc !== url) {
      this._audio.setAttribute("src", url);
      this._lastMediaTime = null;
    }
    this._applyMediaSettings(this._audio, state, attrs);
    this._audio.classList.remove("hidden");
  }

  _applyMediaSettings(element, state, attrs) {
    element.muted = Boolean(attrs.is_volume_muted);
    if (typeof attrs.volume_level === "number") {
      element.volume = attrs.volume_level;
    }

    const repeat = attrs.repeat;
    element.loop = repeat === "one" || repeat === "all";

    const position = this._computePosition(state, attrs);
    if (typeof position === "number" && !Number.isNaN(position)) {
      const delta = Math.abs(element.currentTime - position);
      if (delta > 1) {
        element.currentTime = position;
      }
    }

    if (state === "playing") {
      element.play().catch(() => undefined);
    } else if (state === "paused") {
      element.pause();
    }
  }

  _reportState(
    state,
    mediaPosition,
    mediaDuration,
    volumeLevel,
    isVolumeMuted,
    repeat,
    shuffle,
    force = false
  ) {
    if (!this._config || !this._hass) {
      return;
    }

    const payload = { entity_id: this._config.entity };
    if (state) {
      payload.state = state;
    }
    if (
      typeof mediaPosition === "number" &&
      Number.isFinite(mediaPosition) &&
      mediaPosition >= 0
    ) {
      payload.media_position = mediaPosition;
    }
    if (
      typeof mediaDuration === "number" &&
      (mediaDuration === 0 ||
        (Number.isFinite(mediaDuration) && mediaDuration > 0))
    ) {
      payload.media_duration = mediaDuration;
    }
    if (typeof volumeLevel === "number" && Number.isFinite(volumeLevel)) {
      payload.volume_level = volumeLevel;
    }
    if (typeof isVolumeMuted === "boolean") {
      payload.is_volume_muted = isVolumeMuted;
    }
    if (typeof repeat === "string") {
      payload.repeat = repeat;
    }
    if (typeof shuffle === "boolean") {
      payload.shuffle = shuffle;
    }

    const payloadKey = JSON.stringify(payload);
    if (!force && this._lastReportPayload === payloadKey) {
      return;
    }
    this._lastReportPayload = payloadKey;
    this._hass.callService("ha_dashboard_player", "report_state", payload);
  }

  _handleMediaPlay(event) {
    const element = event?.target;
    if (!element) {
      return;
    }
    if (element.classList.contains("hidden")) {
      return;
    }
    if (element.readyState < 1) {
      return;
    }
    this._reportState(
      element.currentTime,
      element.duration,
      element.volume,
      element.muted
    );
  }

  _handleMediaPause(event) {
    const element = event?.target;
    if (!element) {
      return;
    }
    if (element.classList.contains("hidden")) {
      return;
    }
    if (element.readyState < 1) {
      return;
    }
    this._reportState(
      element.currentTime,
      element.duration,
      element.volume,
      element.muted
    );
  }

  _handleMediaTimeUpdate(event) {
    const element = event?.target;
    if (!element) {
      return;
    }
    if (element.classList.contains("hidden")) {
      return;
    }
    if (element.readyState < 1) {
      return;
    }
    if (!Number.isFinite(element.duration)) {
      return;
    }

    const now = Date.now();
    if (now - this._lastPositionReport < 2000) {
      return;
    }
    this._lastPositionReport = now;

    if (typeof element.currentTime === "number" && this._lastMediaTime !== null) {
      if (element.currentTime + 0.5 < this._lastMediaTime) {
        this._reportState(null, 0, element.duration, null, null, null, null, true);
      }
    }
    this._lastMediaTime = element.currentTime;

    this._reportState(
      null,
      element.currentTime,
      element.duration,
      element.volume,
      element.muted
    );
  }

  _handleMediaSeeked(event) {
    const element = event?.target;
    if (!element) {
      return;
    }
    if (element.classList.contains("hidden")) {
      return;
    }
    if (this._entityState !== "playing" && this._entityState !== "paused") {
      return;
    }
    if (element.readyState < 1) {
      return;
    }
    this._reportState(
      null,
      element.currentTime,
      element.duration,
      element.volume,
      element.muted
    );
  }

  _handleMediaLoaded(event) {
    const element = event?.target;
    if (!element) {
      return;
    }
    if (element.classList.contains("hidden")) {
      return;
    }
    if (element.readyState < 1) {
      return;
    }
    this._reportState(
      null,
      element.currentTime,
      element.duration,
      element.volume,
      element.muted
    );
  }

  _handleMediaDuration(event) {
    const element = event?.target;
    if (!element) {
      return;
    }
    if (element.classList.contains("hidden")) {
      return;
    }
    if (!Number.isFinite(element.duration)) {
      return;
    }
    this._reportState(null, element.currentTime, element.duration, null, null);
  }

  _handleMediaVolume(event) {
    const element = event?.target;
    if (!element) {
      return;
    }
    if (element.classList.contains("hidden")) {
      return;
    }
    if (this._entityState !== "playing" && this._entityState !== "paused") {
      return;
    }
    this._reportState(
      null,
      element.currentTime,
      element.duration,
      element.volume,
      element.muted
    );
  }

  _handleMediaEnded(event) {
    if (!this._config || !this._hass) {
      return;
    }

    const element = event?.target;
    if (element && element.loop) {
      return;
    }

    this._setIdle();
    this._hass.callService("media_player", "media_stop", {
      entity_id: this._config.entity,
    });
  }

  _computePosition(state, attrs) {
    if (typeof attrs.media_position !== "number") {
      return null;
    }

    let position = attrs.media_position;
    if (state === "playing" && attrs.media_position_updated_at) {
      const updated = Date.parse(attrs.media_position_updated_at);
      if (!Number.isNaN(updated)) {
        const elapsed = (Date.now() - updated) / 1000;
        position += elapsed;
      }
    }

    return position;
  }
}

if (!customElements.get("ha-dashboard-player")) {
  customElements.define("ha-dashboard-player", HADashboardPlayerCard);
}

class HADashboardPlayerEditor extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (this._entityPicker) {
      this._entityPicker.hass = hass;
    }
    this._applyEditorLabels();
  }

  setConfig(config) {
    this._config = { ...DEFAULT_CONFIG, ...config };
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML = `
        <style>
          .form {
            display: grid;
            gap: 12px;
          }
        </style>
        <div class="form">
          <ha-entity-picker
            id="entity"
          ></ha-entity-picker>
          <ha-switch id="show_controls"></ha-switch>
          <ha-formfield for="show_controls"></ha-formfield>
          <ha-switch id="autoplay"></ha-switch>
          <ha-formfield for="autoplay"></ha-formfield>
          <ha-switch id="fullscreen"></ha-switch>
          <ha-formfield for="fullscreen"></ha-formfield>
          <ha-switch id="kiosk_compat"></ha-switch>
          <ha-formfield for="kiosk_compat"></ha-formfield>
          <ha-textfield id="fit"></ha-textfield>
          <ha-textfield id="background"></ha-textfield>
        </div>
      `;

      this._entityPicker = this.shadowRoot.querySelector("#entity");
      this._entityPicker.hass = this._hass;
      if ("includeDomains" in this._entityPicker) {
        this._entityPicker.includeDomains = ["media_player"];
      }
      const filter = (entityId) => this._isDashboardPlayerEntity(entityId);
      if ("entityFilter" in this._entityPicker) {
        this._entityPicker.entityFilter = filter;
      } else if ("filter" in this._entityPicker) {
        this._entityPicker.filter = filter;
      }

      this.shadowRoot
        .querySelector("#show_controls")
        .addEventListener("change", (event) =>
          this._valueChanged("show_controls", event.target.checked)
        );
      this.shadowRoot
        .querySelector("#autoplay")
        .addEventListener("change", (event) =>
          this._valueChanged("autoplay", event.target.checked)
        );
      this.shadowRoot
        .querySelector("#fullscreen")
        .addEventListener("change", (event) =>
          this._valueChanged("fullscreen", event.target.checked)
        );
      this.shadowRoot
        .querySelector("#kiosk_compat")
        .addEventListener("change", (event) =>
          this._valueChanged("kiosk_compat", event.target.checked)
        );
      this.shadowRoot
        .querySelector("#fit")
        .addEventListener("change", (event) =>
          this._valueChanged("fit", event.target.value)
        );
      this.shadowRoot
        .querySelector("#background")
        .addEventListener("change", (event) =>
          this._valueChanged("background", event.target.value)
        );
      this._entityPicker.addEventListener("value-changed", (event) =>
        this._valueChanged("entity", event.detail.value)
      );
    }

    this._applyEditorLabels();

    this._entityPicker.value = this._config.entity || "";
    this.shadowRoot.querySelector("#show_controls").checked =
      Boolean(this._config.show_controls);
    this.shadowRoot.querySelector("#autoplay").checked =
      Boolean(this._config.autoplay);
    this.shadowRoot.querySelector("#fullscreen").checked =
      Boolean(this._config.fullscreen);
    this.shadowRoot.querySelector("#kiosk_compat").checked =
      Boolean(this._config.kiosk_compat);
    this.shadowRoot.querySelector("#fit").value = this._config.fit || "contain";
    this.shadowRoot.querySelector("#background").value =
      this._config.background || "#000000";
  }

  _valueChanged(key, value) {
    if (key === "entity" && value && !this._isDashboardPlayerEntity(value)) {
      return;
    }
    if (!this._config || this._config[key] === value) {
      return;
    }

    const newConfig = { ...this._config, [key]: value };
    this._config = newConfig;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: newConfig },
        bubbles: true,
        composed: true,
      })
    );
  }

  _applyEditorLabels() {
    if (!this.shadowRoot) {
      return;
    }

    const labels = this._localizeLabels();
    const entityPicker = this.shadowRoot.querySelector("#entity");
    if (entityPicker) {
      entityPicker.label = labels.entity;
    }

    this._setFormLabel("show_controls", labels.show_controls);
    this._setFormLabel("autoplay", labels.autoplay);
    this._setFormLabel("fullscreen", labels.fullscreen);
    this._setFormLabel("kiosk_compat", labels.kiosk_compat);

    const fit = this.shadowRoot.querySelector("#fit");
    if (fit) {
      fit.label = labels.fit;
    }

    const background = this.shadowRoot.querySelector("#background");
    if (background) {
      background.label = labels.background;
    }
  }

  _setFormLabel(controlId, label) {
    const field = this.shadowRoot.querySelector(
      `ha-formfield[for="${controlId}"]`
    );
    if (field) {
      field.setAttribute("label", label);
    }
  }

  _localizeLabels() {
    const lang = this._hass?.language || "en";
    const table = LOCALIZATION[lang] || LOCALIZATION.en;
    return {
      entity: table.entity || LOCALIZATION.en.entity,
      show_controls: table.show_controls || LOCALIZATION.en.show_controls,
      autoplay: table.autoplay || LOCALIZATION.en.autoplay,
      fullscreen: table.fullscreen || LOCALIZATION.en.fullscreen,
      kiosk_compat: table.kiosk_compat || LOCALIZATION.en.kiosk_compat,
      fit: table.fit || LOCALIZATION.en.fit,
      background: table.background || LOCALIZATION.en.background,
    };
  }

  _isDashboardPlayerEntity(entityId) {
    const stateObj = this._hass?.states?.[entityId];
    return Boolean(stateObj?.attributes?.ha_dashboard_player);
  }
}

if (!customElements.get("ha-dashboard-player-editor")) {
  customElements.define("ha-dashboard-player-editor", HADashboardPlayerEditor);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ha-dashboard-player",
  name: "HA Dashboard Player",
  description: "Fullscreen media player for dashboards.",
});
