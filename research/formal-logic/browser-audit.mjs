// Read-only audit of the actual dossier kit projection. No npm dependencies.
// Usage: /home/othman/.nix-profile/bin/node research/formal-logic/browser-audit.mjs \
//   research/formal-logic/evidence/dossier/atlas.html [audit-output-directory]
// CHROMIUM overrides the executable. AUDIT_CHROMIUM_NO_SANDBOX=1 is available
// only for hosts whose Chromium sandbox cannot start under the runner.
// This script owns and terminates its browser and isolated temporary profile.

import { spawn } from 'node:child_process';
import { readFile, writeFile, mkdir, mkdtemp, rm } from 'node:fs/promises';
import { resolve, join, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

const html = resolve(process.argv[2] || 'research/formal-logic/evidence/dossier/atlas.html');
const output = resolve(process.argv[3] || join(dirname(html), 'browser-audit'));
const chromium = process.env.CHROMIUM || '/home/othman/.nix-profile/bin/chromium';
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const report = {
  schema: 'enchant.formal.dossier-browser-audit.v1', html, chromium,
  started: new Date().toISOString(), checks: [], screenshots: [], viewports: [],
  javascriptExceptions: [], externalRequests: [],
  scope: {
    readOnly: true, feedbackSubmitted: false, applicationStarted: false,
    claim: 'Rendered dossier navigation, layout bounds and interaction only; no semantic or solver qualification.',
    fullscreen: 'Kit expansion/dialog behavior, not the browser Fullscreen API.'
  },
  manualReviewRequired: ['Read desktop and phone screenshots for legibility, clipping, hierarchy and comfortable navigation.']
};
let browser, cdp, profile, closing, session;
let stderr = '';
const started = Date.now();

class CDP {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.id = 0;
    this.pending = new Map();
    this.listeners = [];
    this.ready = new Promise((resolve, reject) => {
      this.ws.addEventListener('open', resolve, { once: true });
      this.ws.addEventListener('error', reject, { once: true });
    });
    this.ws.addEventListener('message', event => {
      const message = JSON.parse(String(event.data));
      if (message.id) {
        const request = this.pending.get(message.id);
        if (!request) return;
        this.pending.delete(message.id); clearTimeout(request.timer);
        if (message.error) request.reject(new Error(JSON.stringify(message.error)));
        else request.resolve(message.result);
      } else for (const listener of this.listeners) listener(message);
    });
    this.ws.addEventListener('close', () => {
      for (const request of this.pending.values()) {
        clearTimeout(request.timer); request.reject(new Error('CDP connection closed'));
      }
      this.pending.clear();
    });
  }
  async send(method, params = {}, sessionId) {
    await this.ready;
    if (Date.now() - started > 240000) throw new Error('Audit exceeded its four minute ceiling');
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id); reject(new Error(`CDP timeout: ${method}`));
      }, 12000);
      this.pending.set(id, { resolve, reject, timer });
      this.ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  }
}

async function cleanup() {
  if (closing) return closing;
  closing = (async () => {
    if (cdp && cdp.ws.readyState === WebSocket.OPEN) {
      await cdp.send('Browser.close').catch(() => {});
      cdp.ws.close();
    }
    if (browser && browser.exitCode === null) {
      try { process.kill(-browser.pid, 'SIGTERM'); } catch {}
      for (let n = 0; n < 20 && browser.exitCode === null; n++) await delay(100);
      if (browser.exitCode === null) try { process.kill(-browser.pid, 'SIGKILL'); } catch {}
    }
    if (profile) await rm(profile, { recursive: true, force: true });
  })();
  return closing;
}
for (const [signal, code] of [['SIGINT', 130], ['SIGTERM', 143]]) {
  process.once(signal, async () => { await cleanup(); process.exit(code); });
}

function check(name, passed, details = {}) {
  report.checks.push({ name, passed: Boolean(passed), ...details });
}
async function evaluate(expression) {
  const value = await cdp.send('Runtime.evaluate', {
    expression, returnByValue: true, awaitPromise: true
  }, session);
  if (value.exceptionDetails) throw new Error(value.exceptionDetails.text + ': ' +
    (value.exceptionDetails.exception?.description || expression.slice(0, 140)));
  return value.result.value;
}
async function settle() {
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
}
async function click(selector) {
  const point = await evaluate(`(() => {
    const element=document.querySelector(${JSON.stringify(selector)});
    if(!element) throw Error('Missing control: '+${JSON.stringify(selector)});
    if(element.disabled) throw Error('Disabled control: '+${JSON.stringify(selector)});
    element.scrollIntoView({block:'center',inline:'nearest'});
    const r=element.getBoundingClientRect();
    const x=Math.max(1,Math.min(innerWidth-2,r.x+r.width/2));
    const y=Math.max(1,Math.min(innerHeight-2,r.y+r.height/2));
    const hit=document.elementFromPoint(x,y);
    if(!hit || !(element===hit || element.contains(hit))) throw Error('Control is obscured: '+${JSON.stringify(selector)});
    return {x,y};
  })()`);
  await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', ...point, button: 'left', clickCount: 1 }, session);
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', ...point, button: 'left', clickCount: 1 }, session);
  await settle();
}
async function screenshot(name) {
  const result = await cdp.send('Page.captureScreenshot', {
    format: 'png', captureBeyondViewport: false, fromSurface: true
  }, session);
  const bytes = Buffer.from(result.data, 'base64');
  const path = join(output, `${name}.png`);
  await writeFile(path, bytes);
  report.screenshots.push({ name, path, sha256: hash(bytes) });
}
async function graphState(selector) {
  return evaluate(`(() => {
    const g=document.querySelector(${JSON.stringify(selector)});
    const active=g.querySelector('.sg-stage > [data-view]:not([hidden])');
    const work=g.querySelector('.sg-workbench');
    const rect=work.getBoundingClientRect();
    return {view:active?.dataset.view, graph:g.classList.contains('sg-graph-mode'),
      expanded:g.classList.contains('sg-expanded'),modal:work.getAttribute('aria-modal'),
      bodyImmersed:document.body.classList.contains('sg-immersed'),
      backDisabled:g.querySelector('[data-sg-back]').disabled,
      views:g.querySelectorAll('.sg-stage > [data-view]').length,
      nodes:g.querySelectorAll('.sg-overview .sg-node').length,
      focusOnExpand:document.activeElement===g.querySelector('[data-sg-expand]'),
      rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},
      page:{width:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth}};
  })()`);
}

try {
  await mkdir(output, { recursive: true });
  const manifest = JSON.parse(await readFile(`${html}.render.json`, 'utf8'));
  report.render = manifest;
  report.htmlSha256 = hash(await readFile(html));
  check('render has no review authoring errors', manifest['authoring-errors'].length === 0,
    { errors: manifest['authoring-errors'] });
  check('HTML matches render manifest', report.htmlSha256 === manifest['html-sha256']);

  profile = await mkdtemp(join(tmpdir(), 'formal-dossier-audit-'));
  const flags = [
    '--headless=new', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
    `--user-data-dir=${profile}`, '--disable-background-networking', '--disable-extensions',
    '--disable-sync', '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check',
    '--hide-scrollbars', 'about:blank'
  ];
  if (process.getuid?.() === 0 || process.env.AUDIT_CHROMIUM_NO_SANDBOX === '1') flags.unshift('--no-sandbox');
  browser = spawn(chromium, flags, { detached: true, stdio: ['ignore', 'ignore', 'pipe'] });
  let spawnError;
  browser.on('error', error => { spawnError = error; });
  browser.stderr.on('data', data => { stderr = (stderr + data.toString()).slice(-16000); });
  let activePort;
  for (let n = 0; n < 150; n++) {
    if (spawnError) throw spawnError;
    if (browser.exitCode !== null) throw new Error(`Chromium exited early: ${browser.exitCode}\n${stderr}`);
    try { activePort = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).trim().split('\n'); break; }
    catch { await delay(100); }
  }
  if (!activePort) throw new Error('Chromium did not publish its debugging endpoint');
  cdp = new CDP(`ws://127.0.0.1:${activePort[0]}${activePort[1]}`);
  report.browser = await cdp.send('Browser.getVersion');
  const target = await cdp.send('Target.createTarget', { url: 'about:blank' });
  session = (await cdp.send('Target.attachToTarget', { targetId: target.targetId, flatten: true })).sessionId;
  cdp.listeners.push(message => {
    if (message.sessionId !== session) return;
    if (message.method === 'Runtime.exceptionThrown') report.javascriptExceptions.push(message.params.exceptionDetails);
    if (message.method === 'Network.requestWillBeSent' && /^https?:/.test(message.params.request.url))
      report.externalRequests.push({ url: message.params.request.url, method: message.params.request.method });
  });
  await cdp.send('Page.enable', {}, session);
  await cdp.send('Runtime.enable', {}, session);
  await cdp.send('Network.enable', {}, session);
  await cdp.send('Network.setBlockedURLs', { urls: ['http://*', 'https://*'] }, session);
  await cdp.send('Emulation.setEmulatedMedia', {
    features: [{ name: 'prefers-color-scheme', value: 'light' }, { name: 'prefers-reduced-motion', value: 'reduce' }]
  }, session);

  for (const viewport of [{ name: 'desktop', width: 1440, height: 1000, mobile: false },
                          { name: 'phone', width: 390, height: 844, mobile: true }]) {
    console.log(`Auditing ${viewport.name} ${viewport.width}x${viewport.height}`);
    await cdp.send('Emulation.setDeviceMetricsOverride', { ...viewport, name: undefined, deviceScaleFactor: 1 }, session);
    await cdp.send('Page.navigate', { url: pathToFileURL(html).href + '#all' }, session);
    let ready = false;
    for (let n = 0; n < 120; n++) {
      ready = await evaluate("document.readyState==='complete' && !!window.__FORMAL_DOSSIER__ && !!document.querySelector('.screen-graph')? true:false").catch(() => false);
      if (ready) break;
      await delay(50);
    }
    if (!ready) throw new Error(`Dossier did not initialize at ${viewport.name}`);
    await evaluate('window.scrollTo(0,0)');
    await settle();
    const initial = await evaluate(`({title:document.title,graphs:[...document.querySelectorAll('.screen-graph')].map(g=>g.dataset.graph),
      readonly:window.__FORMAL_DOSSIER__.readOnly,
      enabledFeedback:document.querySelectorAll('form.fb button:not(:disabled),form.fb textarea:not(:disabled)').length,
      warnings:[...document.querySelectorAll('.warning')].map(e=>e.innerText),
      width:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,
      overflowing:[...document.querySelectorAll('body *')].filter(e=>{
        const r=e.getBoundingClientRect();return r.right>innerWidth+2 && r.width>0 && getComputedStyle(e).position!=='fixed';
      }).slice(0,16).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,
                             right:e.getBoundingClientRect().right,text:e.innerText?.slice(0,90)}))})`);
    const record = { ...viewport, initial, graphs: [] };
    report.viewports.push(record);
    check(`${viewport.name}: expected graph count`, initial.graphs.length === manifest['review-blocks'], { count: initial.graphs.length });
    check(`${viewport.name}: feedback is read only`, initial.readonly && initial.enabledFeedback === 0);
    check(`${viewport.name}: no rendered warnings`, initial.warnings.length === 0, { warnings: initial.warnings });
    check(`${viewport.name}: no page horizontal overflow`, initial.scrollWidth <= initial.width + 2, initial);
    await screenshot(`${viewport.name}-overview`);

    for (const id of initial.graphs) {
      const selector = `.screen-graph[data-graph=${JSON.stringify(id)}]`;
      await click(`${selector} [data-sg-reset]`);
      const before = await graphState(selector);
      const destination = await evaluate(`(() => {
        const g=document.querySelector(${JSON.stringify(selector)});
        const active=g.querySelector('.sg-stage > [data-view]:not([hidden])');
        const edge=active.querySelector('.review-related [data-sg-to]:not([data-sg-navigation])');
        const related=edge || active.querySelector('.review-related [data-sg-to]');
        const any=related || [...active.querySelectorAll('[data-sg-to]')].find(b=>b.dataset.sgTo!==active.dataset.view);
        return {target:any?.dataset.sgTo,semanticEdge:!!edge,relatedLink:!!related};
      })()`);
      if (!destination.target) throw new Error(`Graph ${id} has no navigable second topic`);
      const detailLink = `${selector} .sg-stage > [data-view]:not([hidden]) ` +
        (destination.relatedLink ? '.review-related ' : '') +
        `[data-sg-to=${JSON.stringify(destination.target)}]` +
        (destination.semanticEdge ? ':not([data-sg-navigation])' : '');
      await click(detailLink);
      const navigated = await graphState(selector);
      check(`${viewport.name}/${id}: topic navigation`, navigated.view === destination.target && !navigated.backDisabled, { destination });
      await click(`${selector} [data-sg-back]`);
      const backed = await graphState(selector);
      check(`${viewport.name}/${id}: Back restores previous topic`, backed.view === before.view);

      if (id === 'semantic-design') await screenshot(`${viewport.name}-semantic-detail`);
      await click(`${selector} [data-sg-mode]`);
      const mapped = await graphState(selector);
      check(`${viewport.name}/${id}: map represents every topic`, mapped.graph && mapped.nodes === mapped.views, mapped);
      if (id === 'semantic-design') await screenshot(`${viewport.name}-semantic-map`);
      await click(`${selector} .sg-overview .sg-node[data-sg-to=${JSON.stringify(destination.target)}]`);
      const selected = await graphState(selector);
      check(`${viewport.name}/${id}: map selection opens detail`, selected.view === destination.target && !selected.graph);
      await click(`${selector} [data-sg-back]`);

      await click(`${selector} [data-sg-expand]`);
      const expanded = await graphState(selector);
      check(`${viewport.name}/${id}: full-screen dialog`, expanded.expanded && expanded.bodyImmersed && expanded.modal === 'true' &&
        Math.abs(expanded.rect.x) < 2 && Math.abs(expanded.rect.y) < 2 && Math.abs(expanded.rect.width - viewport.width) < 3 &&
        Math.abs(expanded.rect.height - viewport.height) < 3, expanded);
      if (id === 'semantic-design') await screenshot(`${viewport.name}-semantic-fullscreen`);
      await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }, session);
      await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }, session);
      await settle();
      const escaped = await graphState(selector);
      check(`${viewport.name}/${id}: Escape exits and restores focus`, !escaped.expanded && !escaped.bodyImmersed && escaped.focusOnExpand, escaped);
      check(`${viewport.name}/${id}: detail stays within page width`, escaped.page.scrollWidth <= escaped.page.width + 2, escaped.page);
      record.graphs.push({ id, start: before.view, destination, navigated, mapped, expanded, escaped });
    }

    const palette = await evaluate("({theme:document.documentElement.dataset.theme||'light',bg:getComputedStyle(document.body).backgroundColor})");
    await click('#theme');
    const dark = await evaluate("({theme:document.documentElement.dataset.theme,bg:getComputedStyle(document.body).backgroundColor})");
    check(`${viewport.name}: theme changes palette`, dark.theme === 'dark' && dark.bg !== palette.bg, { before: palette, after: dark });
    await evaluate("document.querySelector('[data-graph=\"semantic-design\"]').scrollIntoView({block:'start'})");
    await settle();
    await screenshot(`${viewport.name}-semantic-dark`);
    await click('#theme');
    const light = await evaluate('document.documentElement.dataset.theme');
    check(`${viewport.name}: theme restores light`, light === 'light');
  }
  check('no JavaScript exceptions', report.javascriptExceptions.length === 0, { count: report.javascriptExceptions.length });
  check('standalone document makes no external network requests', report.externalRequests.length === 0, { requests: report.externalRequests });
} catch (error) {
  report.fatal = { message: error.message, stack: error.stack };
  check('audit completed', false, { error: error.message });
  process.exitCode = 1;
} finally {
  await cleanup();
  report.finished = new Date().toISOString();
  report.browserTerminated = !browser || browser.exitCode !== null || browser.signalCode !== null;
  report.passed = !report.fatal && report.checks.every(c => c.passed) && report.browserTerminated;
  if (!report.passed) process.exitCode = 1;
  report.stderrTail = stderr;
  await mkdir(output, { recursive: true });
  await writeFile(join(output, 'audit.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ audit: join(output, 'audit.json'), passed: report.passed,
    checks: report.checks.length, failed: report.checks.filter(c => !c.passed).map(c => c.name), screenshots: report.screenshots.length }));
}
