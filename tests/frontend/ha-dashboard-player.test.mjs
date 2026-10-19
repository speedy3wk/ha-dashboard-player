import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../../custom_components/ha_dashboard_player/frontend/ha-dashboard-player.js", import.meta.url),
  "utf8",
);

function setup(config = {}) {
  class Element extends EventTarget {
    constructor() {
      super();
      this.attributes = new Map();
      this.classes = new Set();
      this.classList = {
        add: (name) => this.classes.add(name),
        remove: (name) => this.classes.delete(name),
        toggle: (name, enabled) => enabled ? this.classes.add(name) : this.classes.delete(name),
      };
      this.style = { setProperty() {} };
      this.textContent = "";
      this.isConnected = false;
      this.currentTime = 10;
      this.duration = 120;
      this.readyState = 4;
      this.networkState = 1;
      this.paused = false;
      this.seeking = false;
      this.ended = false;
      this.playbackRate = 1;
      this.volume = 1;
      this.videoWidth = 3840;
      this.videoHeight = 2160;
      this.buffered = { length: 1, start: () => 0, end: () => 20 };
      this.quality = { totalVideoFrames: 100, droppedVideoFrames: 5 };
      this.getVideoPlaybackQuality = () => this.quality;
    }
    setAttribute(name, value) { this.attributes.set(name, value); }
    hasAttribute(name) { return this.attributes.has(name); }
    removeAttribute(name) { this.attributes.delete(name); }
    getBoundingClientRect() { return { width: 1920, height: 1080 }; }
    pause() { this.paused = true; }
    play() { this.paused = false; return Promise.resolve(); }
    load() {}
    attachShadow() {
      const nodes = new Map(["video", "audio", "img", ".debug"].map((name) => [name, new Element()]));
      this.shadowRoot = {
        appendChild() {},
        querySelector: (selector) => nodes.get(selector),
      };
    }
  }
  const registry = new Map();
  const timers = new Map();
  const reports = [];
  let time = 1000;
  let nextTimer = 0;
  const context = vm.createContext({
    HTMLElement: Element,
    document: {
      createElement: () => ({ content: { cloneNode() {} } }),
      querySelector: () => null,
      visibilityState: "visible",
    },
    navigator: { language: "en", userAgent: "Test browser" },
    window: { devicePixelRatio: 1 },
    performance: { now: () => time },
    setInterval: (callback, delay) => {
      const id = ++nextTimer;
      timers.set(id, { callback, delay });
      return id;
    },
    clearInterval: (id) => timers.delete(id),
    console: { info() {}, warn() {}, debug() {} },
    customElements: {
      get: (name) => registry.get(name),
      define: (name, value) => registry.set(name, value),
    },
  });
  vm.runInContext(source, context);
  const Card = registry.get("ha-dashboard-player");
  const card = new Card();
  card.setConfig({ entity: "media_player.test", ...config });
  const state = {
    state: "playing",
    attributes: { media_url: "https://example.invalid/video?authSig=secret", media_kind: "video" },
  };
  const hass = {
    language: "en",
    states: { "media_player.test": state },
    callService: (...args) => { reports.push(args); return Promise.resolve(); },
  };
  return {
    card, Card, hass, state, timers, reports,
    tick(milliseconds = 1000) {
      time += milliseconds;
      for (const { callback } of timers.values()) callback();
    },
    connect() {
      card.isConnected = true;
      card.connectedCallback();
    },
  };
}

test("diagnostics are opt-in and exposed with localized editor labels", () => {
  const { card, Card, timers } = setup();
  card.isConnected = true;
  card.connectedCallback();
  assert.equal(card._debug, null);
  assert.equal(timers.size, 0);
  assert.ok(card._debugElement.classes.has("hidden"));
  const form = Card.getConfigForm();
  assert.ok(form.schema.flatMap((item) => item.schema || []).some((item) => item.name === "debug"));
  assert.equal(form.computeLabel({ name: "debug" }), "Show playback diagnostics");
  assert.match(form.computeHelper({ name: "debug" }), /Read-only/);
});

test("timer starts only while connected, stays unique and is cleaned up", () => {
  const { card, connect, timers } = setup({ debug: true });
  assert.equal(timers.size, 0);
  connect();
  card._syncDebug();
  assert.equal(timers.size, 1);
  assert.equal([...timers.values()][0].delay, 1000);
  card.disconnectedCallback();
  card.isConnected = false;
  assert.equal(timers.size, 0);
  connect();
  assert.equal(timers.size, 1);
  card.setConfig({ entity: "media_player.test", debug: false });
  assert.equal(timers.size, 0);
  assert.equal(card._debugElement.textContent, "");
  assert.equal(card._debug, null);
});

test("overlay measures interval frame rate, drops, buffer and dimensions without exposing URLs", async () => {
  const { card, hass, connect, tick } = setup({ debug: true });
  connect();
  card.hass = hass;
  await Promise.resolve();
  tick();
  assert.match(card._debugElement.textContent, /frames\/s: -/);
  card._elements.video.quality = { totalVideoFrames: 160, droppedVideoFrames: 8 };
  tick();
  const text = card._debugElement.textContent;
  assert.match(text, /frames\/s: 57.0/);
  assert.match(text, /dropped: 8 \(5.0%\) \| drops\/interval: 3/);
  assert.match(text, /buffer: 10.0 s/);
  assert.match(text, /3840x2160 \| CSS: 1920x1080/);
  assert.match(text, /not exposed by the browser/);
  assert.doesNotMatch(text, /secret|authSig|example.invalid/);
});

test("unsupported frame API, frame counter resets and disjoint buffers are handled", async () => {
  const { card, hass, connect, tick } = setup({ debug: true });
  connect();
  card.hass = hass;
  await Promise.resolve();
  tick();
  card._elements.video.quality = { totalVideoFrames: 1, droppedVideoFrames: 0 };
  tick();
  assert.match(card._debugElement.textContent, /frames\/s: -/);
  card._elements.video.getVideoPlaybackQuality = undefined;
  card._elements.video.buffered = {
    length: 2,
    start: (i) => [0, 30][i],
    end: (i) => [5, 40][i],
  };
  tick();
  assert.match(card._debugElement.textContent, /n\/a \(API\)/);
  assert.match(card._debugElement.textContent, /buffer: 0.0 s/);
});

test("events and HA corrections are distinct and preserve the seek tolerance", async () => {
  const { card, hass, connect, tick } = setup({ debug: true });
  connect();
  card.hass = hass;
  await Promise.resolve();
  const video = card._elements.video;
  video.dispatchEvent(new Event("waiting"));
  video.dispatchEvent(new Event("stalled"));
  video.dispatchEvent(new Event("seeking"));
  card._elements.audio.dispatchEvent(new Event("waiting"));
  card._applyPlayback(video, "playing", { media_position: 11.5 });
  assert.equal(video.currentTime, 10);
  assert.equal(card._debug.corrections, 0);
  card._applyPlayback(video, "playing", { media_position: 8 });
  assert.equal(video.currentTime, 8);
  assert.equal(card._debug.corrections, 1);
  tick();
  assert.match(card._debugElement.textContent, /waiting 1 \| stalled 1 \| seeking 1/);
  assert.match(card._debugElement.textContent, /HA seek corrections: 1 \| last delta: -2.0 s/);
});

test("diagnostic ticks neither render, reload, seek nor report playback", async () => {
  const { card, hass, connect, tick, reports } = setup({ debug: true });
  connect();
  card.hass = hass;
  await Promise.resolve();
  const video = card._active.element;
  const renderToken = card._renderToken;
  const loads = card._debug.loads;
  for (let i = 0; i < 10; i++) tick();
  assert.equal(card._active.element, video);
  assert.equal(card._renderToken, renderToken);
  assert.equal(card._debug.loads, loads);
  assert.equal(card._debug.corrections, 0);
  assert.equal(video.currentTime, 10);
  assert.equal(reports.length, 0);
  card.hass = { ...hass };
  assert.equal(card._renderToken, renderToken);
  card.hass = {
    ...hass,
    states: { "media_player.test": { ...hass.states["media_player.test"] } },
  };
  assert.equal(card._debug.loads, loads);
  assert.equal(card._active.element, video);
});

test("idle, image and audio diagnostics do not require video APIs", async () => {
  const { card, hass, connect, tick } = setup({ debug: true });
  connect();
  tick();
  assert.match(card._debugElement.textContent, /No active media/);
  for (const kind of ["image", "audio"]) {
    card.hass = {
      ...hass,
      language: "de",
      states: { "media_player.test": {
        state: "playing",
        attributes: { media_url: `https://example.invalid/${kind}`, media_kind: kind },
      } },
    };
    await Promise.resolve();
    tick();
    assert.match(card._debugElement.textContent, new RegExp(kind));
    assert.doesNotMatch(card._debugElement.textContent, /frames\/s/);
  }
  card._unload();
  tick();
  assert.match(card._debugElement.textContent, /Keine aktiven Medien/);
});

test("changing source resets the frame sample but keeps session counters", async () => {
  const { card, hass, state, connect, tick } = setup({ debug: true });
  connect();
  card.hass = hass;
  await Promise.resolve();
  tick();
  card.hass = {
    ...hass,
    states: { "media_player.test": {
      ...state,
      attributes: { ...state.attributes, media_url: "https://example.invalid/next" },
    } },
  };
  await Promise.resolve();
  assert.equal(card._debug.loads, 2);
  tick();
  assert.match(card._debugElement.textContent, /frames\/s: -/);
});

test("toggling diagnostics does not unload or replace an already playing source", async () => {
  const { card, hass, connect, timers } = setup();
  connect();
  card.hass = hass;
  await Promise.resolve();
  const active = card._active;
  for (const debug of [true, false, true]) {
    card.setConfig({ entity: "media_player.test", debug });
    assert.equal(card._active, active);
    assert.equal(card._active.element.currentTime, 10);
    assert.equal(timers.size, debug ? 1 : 0);
  }
  assert.equal(card._debug.loads, 0);
});
