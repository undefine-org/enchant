// connect.spec.js — the socket lifecycle defaults, proven in a real browser.
//
// client.spec.js proves the DIFFER (ops → DOM). This proves the other half of
// priv/lib/live/client.js: connect() itself — the heartbeat that holds a quiet
// page under the server's 120s idle timeout (web/upgrade), and the
// auto-reconnect that brings a culled socket back. No server is started: a
// FakeWebSocket stands in, so what is asserted is the client's behaviour given
// the DEFAULTS the apps rely on (a shell passing no opts) plus the two opt-outs.
//
// Run:  cd test/browser && npx playwright test connect.spec.js

const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const clientJs = fs.readFileSync(
  path.join(__dirname, "../../priv/lib/live/client.js"),
  "utf8"
);

// a WebSocket that never talks to a server. Every instance is recorded, opens
// on the next tick, and close() fires onclose synchronously — so a test can
// close one socket and watch a fresh one appear (or not) with the real timers.
const FAKE = `
window.__sockets = [];
window.WebSocket = function (url) {
  var self = this;
  this.url = url; this.sent = []; this.readyState = 0;
  window.__sockets.push(this);
  setTimeout(function () { self.readyState = 1; if (self.onopen) self.onopen(); }, 0);
};
window.WebSocket.CONNECTING = 0;
window.WebSocket.OPEN = 1;
window.WebSocket.CLOSING = 2;
window.WebSocket.CLOSED = 3;
window.WebSocket.prototype.send = function (d) { this.sent.push(d); };
window.WebSocket.prototype.close = function () {
  this.readyState = 3;
  if (this.onclose) this.onclose();
};
`;

async function boot(page, opts) {
  await page.setContent('<div id="live-root"></div>');
  await page.addScriptTag({ content: FAKE });
  await page.addScriptTag({ content: clientJs });
  await page.evaluate(
    (o) => window.Live.connect(Object.assign(
      { root: document.getElementById("live-root"), url: "ws://fake/ws" }, o)),
    opts || {}
  );
}

const pingsOf = (page) =>
  page.evaluate(() => window.__sockets.map((s) => s.sent.filter((d) => d === '["ping"]').length));

test("mount restores SSR text boundaries before ordinary patch frames", async ({ page }) => {
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, "fixture.json"), "utf8")).fragments;
  await boot(page, { heartbeatMs: 0, reconnect: false });
  await page.waitForFunction(() => window.__sockets[0].readyState === 1);
  await page.evaluate(f => {
    const socket = window.__sockets[0];
    socket.onmessage({ data: JSON.stringify(["mount", f.mount,
      { "input-ack": true, "text-layout": f["text-layout"] }]) });
    f.patches.forEach(patch => socket.onmessage({ data: JSON.stringify(["patch", patch.ops]) }));
  }, fixture);
  await expect(page.locator("label span")).toHaveText("couvertures");
  await expect(page.locator("p")).toHaveText("🙂 مرحبا après");
  expect(await page.evaluate(() => Live.root.__liveInputAck)).toBe(true);
  expect(errors).toEqual([]);
});

// ── the heartbeat ─────────────────────────────────────────────────────

test("heartbeat: a ['ping'] frame per heartbeatMs, and no stray traffic", async ({ page }) => {
  await boot(page, { heartbeatMs: 40 });
  await page.waitForTimeout(300);
  const counts = await pingsOf(page);
  expect(counts.length).toBe(1);
  expect(counts[0]).toBeGreaterThanOrEqual(2);   // ~7 in 300ms; >=2 is the claim
  // every frame it sent is the ping (nothing else is invented on the wire)
  const all = await page.evaluate(() => window.__sockets[0].sent);
  expect(all.every((d) => d === '["ping"]')).toBe(true);
});

test("heartbeat: 0 disables it", async ({ page }) => {
  await boot(page, { heartbeatMs: 0 });
  await page.waitForTimeout(300);
  expect((await pingsOf(page))[0]).toBe(0);
});

// The default cadence is the one that has to beat the server's 120s idle
// timeout, so it is pinned by observation, not by reading a constant: 30s.
test("heartbeat: the DEFAULT is 30s — quiet at 1s, beating by 31s", async ({ page }) => {
  test.setTimeout(45000);
  await boot(page);                       // no opts — what every shell passes
  await page.waitForTimeout(1000);
  expect((await pingsOf(page))[0]).toBe(0);
  await page.waitForFunction(
    () => window.__sockets[0].sent.filter((d) => d === '["ping"]').length >= 1,
    null, { timeout: 33000 });
  expect((await pingsOf(page))[0]).toBeGreaterThanOrEqual(1);
});

// ── reconnect ─────────────────────────────────────────────────────────

test("reconnect: a closed socket comes back with no opts (the default)", async ({ page }) => {
  await boot(page);                       // no opts
  await page.waitForFunction(() => window.__sockets.length === 1 && window.__sockets[0].readyState === 1);
  await page.evaluate(() => window.Live.ws.close());
  await page.waitForFunction(() => window.__sockets.length === 2, null, { timeout: 5000 });
  await page.waitForFunction(() => window.__sockets[1].readyState === 1);
  expect(await page.evaluate(() => document.documentElement.getAttribute("data-live"))).toBe("1");
});

test("reconnect: {reconnect:false} opts out", async ({ page }) => {
  await boot(page, { reconnect: false });
  await page.waitForFunction(() => window.__sockets.length === 1 && window.__sockets[0].readyState === 1);
  await page.evaluate(() => window.Live.ws.close());
  await page.waitForTimeout(1200);         // > the 500ms first backoff
  expect(await page.evaluate(() => window.__sockets.length)).toBe(1);
});

// A reconnect SWAPS `ws` for a new object (openSocket reassigns it), and the
// click handler reads `ws.__navigate` off whatever is current. Attach the
// navigator to only the first socket and the one a reconnect brings back has
// none: the click is preventDefault'd, no navigate frame is ever sent, and the
// URL never moves — a dead in-app link on a socket that reports itself live.
// Silent, and only after a drop, which is what makes it look intermittent.
test("reconnect: an in-app link still navigates on the socket that came back", async ({ page }) => {
  await boot(page);
  await page.waitForFunction(() => window.__sockets.length === 1 && window.__sockets[0].readyState === 1);
  await page.evaluate(() => {
    document.getElementById("live-root").innerHTML = '<a href="/lib/dossier-mci">dossier-mci</a>';
  });
  await page.evaluate(() => window.Live.ws.close());
  await page.waitForFunction(() => window.__sockets.length === 2 && window.__sockets[1].readyState === 1);

  await page.click("a[href='/lib/dossier-mci']");

  // the click must reach the server over the socket that is actually open
  await page.waitForFunction(() => window.__sockets[1].sent.length > 0, null, { timeout: 2000 });
  expect(await page.evaluate(() => window.__sockets[1].sent))
    .toEqual(['["event",["navigate","/lib/dossier-mci"],{}]']);
});

// A navigation moves the URL bar synchronously (pushState) but the page only
// changes when the server receives the navigate event and re-projects. If the
// socket is not OPEN at click time the frame used to be DROPPED (sendFrame's
// CLOSED branch), so the URL moved and the page did not — and because a
// reconnect RESUMES the same server session at its now-stale route, the
// divergence survived the reconnect: only a full reload recovered. Navigation
// now CONVERGES: the route is buffered while the socket is down and flushed on
// reopen, so the page always catches up to the address bar.
test("reconnect: a link clicked while the socket is DOWN still navigates on reopen", async ({ page }) => {
  await boot(page);                                 // reconnect is ON by default
  await page.waitForFunction(() => window.__sockets.length === 1 && window.__sockets[0].readyState === 1);
  await page.evaluate(() => {
    document.getElementById("live-root").innerHTML = '<a href="/lib/dossier-mci">dossier-mci</a>';
  });
  // close the socket and click WHILE IT IS CLOSED — before the 500ms backoff
  // reopens it. The same connect() closure will reconnect on its own timer, so
  // its buffered route (pendingNav) survives to the reopen.
  await page.evaluate(() => window.Live.ws.close());
  await page.click("a[href='/lib/dossier-mci']");
  // the frame was NOT dropped and NOT yet on any wire: socket #1 is closed,
  // socket #2 has not opened, so nothing was sent — the route is buffered.
  // (pushState's URL move is not asserted here: this harness runs on
  // about:blank, where a same-origin pushState to /lib/… is blocked; the
  // headless-Chrome repro against the real app confirms the URL moves.)
  expect(await page.evaluate(() => window.__sockets[0].sent.filter(function (d) { return d.indexOf("navigate") >= 0; }))).toEqual([]);
  // the same-closure reconnect brings socket #2; onopen flushes the buffered route
  await page.waitForFunction(() => window.__sockets.length === 2 && window.__sockets[1].readyState === 1);
  await page.waitForFunction(
    () => window.__sockets[1].sent.some(function (d) { return d === '["event",["navigate","/lib/dossier-mci"],{}]'; }),
    null, { timeout: 2000 });
});

// ── the session id ───────────────────────────────────────────────────
//
// The server keys the SESSION (locals, last-seen tree, subscriptions) on
// `live-sid`, so a reconnect resumes instead of re-mounting. Two things have
// to hold for that: the id is on every socket URL, and it is the SAME one
// across a reconnect of the same page load — a fresh id per reconnect would
// be a fresh session, which is the bug this exists to prevent.

test("session: every socket URL carries the sid, identical across a reconnect", async ({ page }) => {
  await boot(page);
  await page.waitForFunction(() => window.__sockets.length === 1 && window.__sockets[0].readyState === 1);
  const first = await page.evaluate(() => window.__sockets[0].url);
  expect(first).toMatch(/[?&]live-sid=[0-9a-f]{32}/);
  await page.evaluate(() => window.Live.ws.close());
  await page.waitForFunction(() => window.__sockets.length === 2, null, { timeout: 5000 });
  const second = await page.evaluate(() => window.__sockets[1].url);
  expect(second).toBe(first);
});

test("session: a fresh connect() mints a NEW sid (a reload is a new session)", async ({ page }) => {
  await boot(page);
  await page.waitForFunction(() => window.__sockets.length === 1 && window.__sockets[0].readyState === 1);
  const first = await page.evaluate(() => window.__sockets[0].url);
  const other = await page.evaluate(() => {
    var before = window.__sockets.length;
    window.Live.connect({ root: document.getElementById("live-root"), url: "ws://fake/ws" });
    return window.__sockets[before].url;
  });
  expect(other).not.toBe(first);
  expect(other).toMatch(/[?&]live-sid=[0-9a-f]{32}/);
});

test("session: reconnect distinguishes an undelivered first mount from a hydrated DOM", async ({ page }) => {
  await boot(page, { heartbeatMs: 0 });
  await page.waitForFunction(() => window.__sockets[0].readyState === 1);
  const first = await page.evaluate(() => window.__sockets[0].url);
  expect(new URL(first).searchParams.get('live-mounted')).toBe('0');
  await page.evaluate(() => window.__sockets[0].close());
  await page.waitForFunction(() => window.__sockets.length === 2 && window.__sockets[1].readyState === 1);
  const lostMount = await page.evaluate(() => window.__sockets[1].url);
  expect(new URL(lostMount).searchParams.get('live-sid')).toBe(new URL(first).searchParams.get('live-sid'));
  expect(new URL(lostMount).searchParams.get('live-mounted')).toBe('0');
  await page.evaluate(() => {
    window.__sockets[1].onmessage({ data: JSON.stringify(['mount', '<input value="retained">', { 'input-ack': true, 'text-layout': [] }]) });
    window.__sockets[1].close();
  });
  await page.waitForFunction(() => window.__sockets.length === 3 && window.__sockets[2].readyState === 1);
  const mounted = await page.evaluate(() => window.__sockets[2].url);
  expect(new URL(mounted).searchParams.get('live-sid')).toBe(new URL(first).searchParams.get('live-sid'));
  expect(new URL(mounted).searchParams.get('live-mounted')).toBe('1');
  expect(await page.locator('input').inputValue()).toBe('retained');
});


test("fragment setting links use native navigation and land on the exact field", async ({ page }) => {
  await page.route("http://live.test/**", route => route.fulfill({
    contentType: "text/html",
    body: "<div style='height:1600px'></div><input id='machine-setting-clamp' value='16'><div style='height:500px'></div>"
  }));
  await page.goto("http://live.test/start");
  await boot(page, { heartbeatMs: 0, reconnect: false });
  await page.waitForFunction(() => window.__sockets[0].readyState === 1);
  await page.evaluate(() => {
    document.getElementById("live-root").innerHTML =
      '<a id="plain" href="/resource/other?tab=settings">Settings</a>' +
      '<a id="source" href="/resource/cutter?tab=settings#machine-setting-clamp">16 mm source</a>';
  });
  await page.click("#plain");
  expect(await page.evaluate(() => window.__sockets[0].sent)).toEqual([
    '["event",["navigate","/resource/other?tab=settings"],{}]'
  ]);
  await page.click("#source");
  await expect(page).toHaveURL("http://live.test/resource/cutter?tab=settings#machine-setting-clamp");
  await expect(page.locator("#machine-setting-clamp")).toHaveValue("16");
  expect(await page.locator("#machine-setting-clamp").evaluate(e => {
    const r=e.getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight;
  })).toBe(true);
});
