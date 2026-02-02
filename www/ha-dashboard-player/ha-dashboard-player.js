/* HA Dashboard Player card */

const DEFAULT_CONFIG = {
  show_controls: false,
  autoplay: true,
  fit: "contain",
  background: "#000000",
  fullscreen: false,
  kiosk_compat: false,
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
      this._setIdle();
      return;
    }

    const attrs = stateObj.attributes || {};
    const state = stateObj.state;
    const mediaUrl = attrs.media_url || attrs.entity_picture || attrs.media_content_id;
    const mediaType = attrs.media_content_type || "";

    if (!mediaUrl || state === "idle" || state === "off") {
      this._setIdle();
      return;
    }

    if (mediaType.startsWith("image")) {
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
  }

  _showVideo(url, state, attrs) {
    this._hideAll();
    if (this._video.src !== url) {
      this._video.src = url;
    }
    this._applyMediaSettings(this._video, state, attrs);
    this._video.classList.remove("hidden");
  }

  _showAudio(url, state, attrs) {
    this._hideAll();
    if (this._audio.src !== url) {
      this._audio.src = url;
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

customElements.define("ha-dashboard-player", HADashboardPlayerCard);

class HADashboardPlayerEditor extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (this._entityPicker) {
      this._entityPicker.hass = hass;
    }
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
            label="Entity"
            allow-custom-entity
          ></ha-entity-picker>
          <ha-switch id="show_controls"></ha-switch>
          <ha-formfield label="Show controls" for="show_controls"></ha-formfield>
          <ha-switch id="autoplay"></ha-switch>
          <ha-formfield label="Autoplay" for="autoplay"></ha-formfield>
          <ha-switch id="fullscreen"></ha-switch>
          <ha-formfield label="Fullscreen (panel)" for="fullscreen"></ha-formfield>
          <ha-switch id="kiosk_compat"></ha-switch>
          <ha-formfield label="Kiosk compat (WebKit)" for="kiosk_compat"></ha-formfield>
          <ha-textfield id="fit" label="Fit (contain | cover | fill)"></ha-textfield>
          <ha-textfield id="background" label="Background (CSS color)"></ha-textfield>
        </div>
      `;

      this._entityPicker = this.shadowRoot.querySelector("#entity");
      this._entityPicker.hass = this._hass;

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
}

customElements.define("ha-dashboard-player-editor", HADashboardPlayerEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ha-dashboard-player",
  name: "HA Dashboard Player",
  description: "Fullscreen media player for dashboards.",
});
