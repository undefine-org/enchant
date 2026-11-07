// mount.spec.js — what the client does to the SERVER-RENDERED page when the
// socket arrives: the ["mount"] that replaces it, and the ["style"] rules it
// adds to <head>. A FakeWebSocket stands in for the server.
//
//   1. The mount used to be a bare `root.innerHTML = html`: text typed into
//      the first paint before the socket mounted vanished, and focus with it.
//      Typed values, ticks, selections, focus and caret now survive; a field
//      the view binds re-sends its value; `<html data-mounted="1">` marks the
//      mount for anything that waits on it.
//   2. live's rules used to be appended at the END of <head>, so its base
//      reset overrode an app's own stylesheet. They now go into the page's
//      <style id="live-style"> (the SSR shell's sheet), or before the first
//      stylesheet when the page has none.
//
// Run:  cd test/browser && npx playwright test mount.spec.js

const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const clientJs = fs.readFileSync(
  process.env.LIVE_CLIENT_SOURCE ||
    path.join(__dirname, "../../priv/lib/live/client.js"),
  "utf8"
);

const FAKE = `
window.WebSocket = function () {
  this.readyState = 1; this.sent = []; window.sock = this;
  setTimeout(() => this.onopen && this.onopen(), 0);
};
WebSocket.OPEN = 1; WebSocket.CONNECTING = 0; WebSocket.CLOSED = 3;
WebSocket.prototype.send = function (s) { this.sent.push(JSON.parse(s)); };
WebSocket.prototype.close = function () {};
`;

async function load(page, head, body) {
  await page.setContent(`<!doctype html><html><head>${head}</head><body>` +
    `<div id="live-root">${body}</div></body></html>`);
  await page.addScriptTag({ content: FAKE });
  await page.addScriptTag({ content: clientJs });
}

async function connect(page) {
  await page.evaluate(() => Live.connect({
    root: document.getElementById("live-root"), url: "ws://fake/ws",
    heartbeatMs: 0, reconnect: false }));
}

async function frame(page, body) {
  await page.evaluate((b) => sock.onmessage({ data: JSON.stringify(b) }), body);
}

// the same view, as SSR painted it and as the socket's mount re-renders it
const FORM =
  '<main><h1>Form</h1><form>' +
  '<input id="title" value="">' +
  '<textarea name="note"></textarea>' +
  '<input name="q" value="ssr">' +
  '<input type="checkbox" name="ok">' +
  '<input type="radio" name="size" value="s" checked><input type="radio" name="size" value="l">' +
  '<select name="pick"><option value="a">A</option><option value="b">B</option></select>' +
  '<div><input placeholder="no id, no name"></div>' +
  '<input name="fresh" value="FRESH">' +
  "</form></main>";

test("typed values, ticks, focus and caret survive the socket's mount", async ({ page }) => {
  await load(page, "", FORM.replace('value="FRESH"', 'value="old"'));
  await page.fill("#title", "typed title");
  await page.fill("textarea[name=note]", "a note typed early");
  await page.fill("input[name=q]", "query");
  await page.check("input[name=ok]");
  await page.check("input[name=size][value=l]");
  await page.selectOption("select[name=pick]", "b");
  await page.fill("input[placeholder]", "by path");
  await page.evaluate(() => {
    const t = document.querySelector("textarea[name=note]");
    t.focus(); t.setSelectionRange(2, 6);
  });

  await connect(page);
  await frame(page, ["mount", FORM, { "input-ack": true }]);

  await expect(page.locator("#title")).toHaveValue("typed title");
  await expect(page.locator("textarea[name=note]")).toHaveValue("a note typed early");
  await expect(page.locator("input[name=q]")).toHaveValue("query");
  await expect(page.locator("input[name=ok]")).toBeChecked();
  await expect(page.locator("input[name=size][value=l]")).toBeChecked();
  await expect(page.locator("input[name=size][value=s]")).not.toBeChecked();
  await expect(page.locator("select[name=pick]")).toHaveValue("b");
  await expect(page.locator("input[placeholder]")).toHaveValue("by path");
  // an untouched field takes what the server now says
  await expect(page.locator("input[name=fresh]")).toHaveValue("FRESH");
  // focus and the selection are back on the NEW textarea
  expect(await page.evaluate(() => {
    const a = document.activeElement;
    return [a.getAttribute("name"), a.selectionStart, a.selectionEnd];
  })).toEqual(["note", 2, 6]);
  // the mount is marked where a test (or an app) can wait for it
  await expect(page.locator("html")).toHaveAttribute("data-mounted", "1");
});

test("a restored field the view binds re-sends its value to the server", async ({ page }) => {
  const view = '<div><input id="draft" value="" ' +
    "data-ev-input='[\"assign\",\"draft\",[\"from\",\"value\"]]'></div>";
  await load(page, "", view);
  await page.fill("#draft", "hello before mount");
  await connect(page);
  await frame(page, ["mount", view, { "input-ack": true }]);
  await expect(page.locator("#draft")).toHaveValue("hello before mount");
  const sent = await page.evaluate(() => sock.sent.filter((f) => f[0] === "event"));
  expect(sent.length).toBe(1);
  expect(sent[0][1]).toEqual(["assign", "draft", ["from", "value"]]);
  expect(sent[0][2].value).toBe("hello before mount");
  // and the controlled field is pending, so the server's stale echo cannot erase it
  await frame(page, ["patch", [["set-attr", [0], "value", ""]]]);
  await expect(page.locator("#draft")).toHaveValue("hello before mount");
});

test("live's rules go before the app's stylesheet, so the app's rules win", async ({ page }) => {
  await load(page, '<style id="app">body{color:rgb(1, 2, 3)}</style>', "<p>x</p>");
  await connect(page);
  await frame(page, ["style", "body{color:rgb(9, 9, 9)}"]);
  expect(await page.evaluate(() => getComputedStyle(document.body).color)).toBe("rgb(1, 2, 3)");
  expect(await page.evaluate(() =>
    Array.from(document.head.querySelectorAll("style")).map((e) => e.id))).toEqual(["live-style", "app"]);
});

test("rules land in the page's own <style id=live-style>, where the shell put it", async ({ page }) => {
  await load(page,
    '<style id="live-style">body{color:rgb(9, 9, 9)}</style>' +
    '<style id="app">body{color:rgb(1, 2, 3)}</style>', "<p>x</p>");
  await connect(page);
  await frame(page, ["style", "body{color:rgb(8, 8, 8)} p{margin:7px}"]);
  expect(await page.evaluate(() => getComputedStyle(document.body).color)).toBe("rgb(1, 2, 3)");
  expect(await page.evaluate(() => getComputedStyle(document.querySelector("p")).marginTop)).toBe("7px");
  expect(await page.evaluate(() => document.querySelectorAll("style").length)).toBe(2);
});
