// verify-workspace.mjs — the generative-editor mockup, end to end.
//
// Drives apps/workspace.bl through the shared kit: one loopback authority and
// one child running the BL client half exactly as the Worker runs it. Proves
//
//   * placement: the view, the reducer and the MOTION CONTRACT are the
//     browser's; the checks are shared; the reader, the mock runtime and every
//     id-choosing change are the server's, and neither the runtime nor a
//     candidate's source ever reaches the client bundle or the wire;
//   * the structural motion contract of docs/design/form-first-interaction.md
//     — every row of its table and its worked example, forward and at the
//     boundary — computed by the BL client from the server's form tree;
//   * evaluation: an `Evaluate form` proposal names path · rev · form, the
//     server evaluates THAT form and appends a receipt to the owning Stream
//     or the file's own activity; a stale revision is refused in the browser
//     before sending AND by the server;
//   * Made / Verified / Saved / Live as four independent decisions, in their
//     only legal order; Save bumps the file's revision, old receipts stay on
//     their captured one; Live changes what evaluation sees, not the file;
//   * the Stream: a spec save guarded by its basis, a comment on a form
//     anchored to path · rev · form, a turn recorded without inventing a
//     model answer, and a new Stream predicted in the browser.

import assert from 'node:assert/strict';
import { startApp, spawnClient, texts, findAll, attr, nonce, sleep, readOut } from './split-test-kit.mjs';

let passed = 0;
const ok = (label) => { passed += 1; console.log('PASS workspace: ' + label); };

const contract = JSON.parse(readOut('workspace.contract.json'));
const manifest = JSON.parse(readOut('workspace.split.json'));
const clientBundle = readOut('workspace-client.mjs');
const digest = contract.digest;

// ── 1. placement ────────────────────────────────────────────────────────────
const where = Object.fromEntries(manifest.functions.map(f => [f.name, f.placement]));
for (const n of ['workspace-view', 'on-event', 'motion', 'climb', 'descend', 'path-in', 'form-view', 'actions'])
  assert.equal(where[n], 'client', n + ' runs in the browser');
for (const n of ['find-form', 'form-src', 'eval-problem', 'decide-problem', 'spec-problem', 'save-spec', 'attach', 'new-stream'])
  assert.equal(where[n], 'shared', n + ' is shared');
for (const n of ['read-source', 'ev', 'apply-builtin', 'load-defs', 'image-forms', 'receipt', 'eval-form', 'decide',
                 'candidate-checks', 'initial-workspace'])
  assert.equal(where[n], 'server', n + ' is the server\'s');
for (const n of ['"js/ev"', '"js/read-source"', '"js/invoices-v1-src"'])
  assert.equal(clientBundle.includes(n), false, n + ' never ships to the browser');
ok('placement: view, reducer and motion in the browser; checks shared; reader, runtime and changes on the server');

// ── the authority and the client ────────────────────────────────────────────
// A commit re-projects and re-checks the whole board (~0.8 s of CPU on an idle
// machine); under load that can pass the default 4 s authority limit. This
// suite asserts content, not latency, so it gives the authority room.
const app = await startApp('workspace', { authorityTimeoutMs: 60000 });
const hello = await app.snapshotNow();
const board0 = hello.board;
assert.equal(board0.files.length, 2);
assert.equal(board0.streams.length, 2);
assert.equal(JSON.stringify(board0).includes('"source"'), false, 'a candidate\'s full source is server-private');
ok('the authority serves two files and two Streams; candidate source stays server-side');

const client = spawnClient('workspace');
await client.next('ready', 0);
let mark = client.frames.length;
client.tell({ kind: 'hello', ...hello });
await client.next('view', mark);

const lastView = () => client.frames.filter(f => f.topic === 'view').at(-1).value;
const awaitView = async (pred, from, label) => {
  const start = Date.now();
  for (;;) {
    const hit = client.frames.slice(from).filter(f => f.topic === 'view' && pred(f.value)).at(-1);
    if (hit) return hit.value;
    if (Date.now() - start > 15000) throw new Error('timed out waiting for ' + label);
    await sleep(10);
  }
};
// the kit sends keywords as ':name'; a handler vector from the view arrives
// encoded with bare names, so the first item is re-marked as a keyword
const asEvent = h => [':' + h[0], ...h.slice(1).map(x => typeof x === 'string' && KEYWORD_ARGS.has(x) ? ':' + x : x)];
const KEYWORD_ARGS = new Set(['source', 'stream', 'verify', 'save', 'live', 'form', 'block']);
const send = async (event, pred, label) => {
  const from = client.frames.length;
  client.tell({ kind: 'event', event });
  return awaitView(pred, from, label);
};
// the text a node renders: its children's strings, never its tag or attrs
const textOf = node => {
  if (typeof node === 'string') return node;
  if (!Array.isArray(node)) return '';
  const kids = attr(node) !== null && typeof node[0] === 'string' ? node.slice(2) : node;
  return kids.map(textOf).join('');
};
const root = tree => findAll(tree, n => Array.isArray(n) && n[0] === 'section' && String(attr(n)?.class).startsWith('ws'))[0];
const keysOf = tree => attr(root(tree)).keys;
const selected = tree => {
  const cell = findAll(tree, n => Array.isArray(n) && n[0] === 'aside')[0];
  const code = cell && findAll(cell, n => Array.isArray(n) && n[0] === 'div' && attr(n)?.class === 'code cell')[0];
  return code ? textOf(code) : null;
};
const cueOf = tree => { const c = findAll(tree, n => Array.isArray(n) && attr(n)?.class === 'cue')[0]; return c ? textOf(c) : ''; };

// ── 2. the motion contract ──────────────────────────────────────────────────
// A file whose top-level forms are exactly the design doc's example:
//   A = (def x 1)   B = (map inc [1 2])   C = (println x)
// is not seeded; the same shapes exist in src/app/invoices.bl, so the table
// is proven on that file and the worked example on its forms.
await send([':persp', ':source'], v => keysOf(v.tree).s !== undefined && texts(v.tree).includes('src/app/invoices.bl'), 'source');
const inv = board0.files[0];
const top = i => inv.forms[i];
const find = (forms, pred) => { for (const f of forms) { if (pred(f)) return f; const k = find(f.kids, pred); if (k) return k; } return null; };

const pick = id => send([':pick', id], v => selected(v.tree) !== null && keysOf(v.tree).j !== undefined, 'pick ' + id);
const press = async (k) => {
  const h = keysOf(lastView().tree)[k];
  assert.ok(Array.isArray(h), 'the view binds ' + k);
  const before = client.frames.length;
  client.tell({ kind: 'event', event: asEvent(h) });
  return awaitView(() => true, before, 'after ' + k);
};
const at = async (k) => { const v = await press(k); return [selected(v.tree), cueOf(v.tree)]; };

// top-level forms of src/app/invoices.bl: 0 (ns …) 1 (def late-fee-rate 5)
// 2 (defn total …) 3 (defn late-fee …) 4 (+ 40 2) 5 (* late-fee-rate 12) 6 (total …)
await pick(top(4).id);
assert.deepEqual(await at('j'), ['+', ''], 'J: first child');
assert.deepEqual(await at('l'), ['40', ''], 'L: next sibling');
assert.deepEqual(await at('l'), ['2', ''], 'L: next sibling');
assert.deepEqual(await at('l'), ['*', ''], 'L at the end: climb to the next parent, first child');
assert.deepEqual(await at('h'), ['2', ''], 'H at the start: climb to the previous parent, last child');
assert.deepEqual(await at('k'), ['(+ 40 2)', ''], 'K: parent');
assert.deepEqual(await at('k'), ['(* late-fee-rate 12)', ''], 'K at top level: next top-level sibling');
ok('J/K/H/L: first child, parent, siblings, and both climb rules land where the table says');

// H/L descend to the DEEPEST executable descendant after a climb
const lateFee = top(3);                                           // (defn late-fee [amount days] (if …))
const vecForm = lateFee.kids[2];                                  // [amount days]
await pick(vecForm.kids[1].id);                                   // days
assert.deepEqual(await at('l'), ['if', ''], 'L from the last vector item climbs to (if …) and descends to its first child');
await pick(top(2).id);                                            // (defn total [items] (reduce + (map :amount items)))
await press('j'); await press('l'); await press('l'); await press('l');
assert.equal(selected(lastView().tree), '(reduce + (map :amount items))');
assert.deepEqual(await at('l'), ['defn', ''], 'L descends into the next top-level form (defn late-fee …)');
const [prevDeep] = await at('h');
assert.equal(prevDeep, 'items', 'H after a climb descends to the deepest last child: items in (map :amount items)');
ok('after a climb, H descends last-child and L first-child to the deepest form');

// boundaries: nothing wraps, the selection stays and the view says why
await pick(top(0).kids[0].id);                                    // ns
assert.deepEqual(await at('h'), ['ns', 'First form']);
await pick(top(0).id);
assert.deepEqual(await at('h'), ['(ns app.invoices)', 'First form']);
const last = inv.forms.at(-1);
await pick(last.id);
assert.deepEqual(await at('k'), ['(total [{:amount 40} {:amount 2}])', 'Already at last top-level form']);
const lastAtom = find([last], f => f.kind === 'number' && f.text === '2');
await pick(lastAtom.id);
assert.deepEqual(await at('l'), ['2', 'Last form']);
assert.deepEqual(await at('j'), ['2', 'No child or next sibling']);
ok('boundaries: First form · Already at last top-level form · Last form · No child or next sibling — no wrap');

// Escape clears; with no selection the view binds no motion and no eval key
await press('Escape');
const cleared = keysOf(lastView().tree);
for (const k of ['j', 'k', 'h', 'l', 'Enter']) assert.equal(cleared[k], undefined, k + ' is unbound with no selection');
ok('Escape clears the selection; with none, j/k/h/l/Enter are not offered at all');

// ── 3. evaluation ───────────────────────────────────────────────────────────
const propose = async (from, label) => (await client.next('propose', from)).value;
const settle = async (proposal, label) => {
  const r = await app.post(proposal);
  assert.ok(r.body && r.body.board, `${label}: the server answered ${r.status} ${r.body && r.body.reason}`);
  const from = client.frames.length;
  client.tell({ kind: 'result', frame: r.body });
  await awaitView(v => v.revision === r.body.revision, from, label);
  return r;
};

await pick(top(5).id);                                             // (* late-fee-rate 12)
mark = client.frames.length;
await press('Enter');
let p = await propose(mark);
assert.equal(p.op, 'eval-form');
assert.deepEqual(p.args, { stream: 0, path: 'src/app/invoices.bl', rev: 1, form: top(5).id });
let r = await settle(p, 'eval');
assert.equal(r.body.ok, true);
let rec = r.body.board.direct.at(-1);
assert.deepEqual([rec.kind, rec.text, rec.result, rec.failed, rec.path, rec.rev, rec.form],
                 ['receipt', '(* late-fee-rate 12)', '60', false, 'src/app/invoices.bl', 1, top(5).id]);
assert.match(rec.runtime, /workspace image · app\.invoices @ rev 1/);
// the seed already holds a Stream receipt for this form; the newest one wins,
// wherever it lives, both inline and in the inspector
const inlineOf = tree => findAll(tree, n => Array.isArray(n) && String(attr(n)?.class).startsWith('inline'))
  .map(textOf).find(t => t.includes('(* late-fee-rate 12)'));
assert.match(inlineOf(lastView().tree), /source activity/, 'the inline receipt is the newest: this file\'s');
assert.match(textOf(findAll(lastView().tree, n => Array.isArray(n) && n[0] === 'aside')[0]), new RegExp('receipt #' + rec.id));
ok('Enter proposes eval-form {path rev form}; the server evaluates that form (60); the newest receipt shows');

await pick(top(2).kids[0].id);                                     // `defn` inside (defn total …)
mark = client.frames.length;
await press('Enter');
r = await settle(await propose(mark), 'eval symbol');
rec = r.body.board.direct.at(-1);
assert.equal(rec.failed, true);
assert.match(rec.result, /Unable to resolve symbol: defn/);
ok('an unbound symbol is an honest error receipt, not a guess');

// ── 4. Made / Verified / Saved / Live ───────────────────────────────────────
await send([':open-stream', 1, 0], v => texts(v.tree).includes('Stream · Invoice edge cases'), 'stream');
const cand = () => r.body.board.streams[0].candidates[0];
mark = client.frames.length;
client.tell({ kind: 'event', event: [':decide', 1, 1, ':save'] });
let refused = await awaitView(v => texts(v.tree).includes('not-verified'), mark, 'save refused');
assert.equal(client.frames.slice(mark).some(f => f.topic === 'propose'), false, 'Save before Verify never reaches the wire');
ok('Save before Verify is refused in the browser (not-verified) and never sent');

mark = client.frames.length;
client.tell({ kind: 'event', event: [':decide', 1, 1, ':verify'] });
r = await settle(await propose(mark), 'verify');
assert.deepEqual([cand().verified, cand().saved, cand().live], [true, false, false]);
assert.deepEqual(cand().checks, ['✓ reads · 8 top-level forms', '✓ loads · 4 vars defined']);
ok('Verify runs the server\'s checks on the candidate: Verified only');

mark = client.frames.length;
client.tell({ kind: 'event', event: [':decide', 1, 1, ':live'] });
r = await settle(await propose(mark), 'live');
assert.deepEqual([cand().verified, cand().saved, cand().live], [true, false, true]);
assert.equal(r.body.board.files[0].rev, 1, 'Live does not write the file');
await send([':persp', ':source'], v => texts(v.tree).includes('image runs a live candidate'), 'live pill');
await pick(top(5).id);
mark = client.frames.length;
await press('Enter');
r = await settle(await propose(mark), 'eval under live');
assert.equal(r.body.board.direct.at(-1).result, '96', 'the image now runs late-fee-rate 8: 8 × 12');
assert.match(r.body.board.direct.at(-1).runtime, /candidate v1 live/);
ok('Make Live changes what evaluation sees (96) without writing the file (still rev 1)');

await send([':open-stream', 1, 0], v => texts(v.tree).includes('Stream · Invoice edge cases'), 'stream');
mark = client.frames.length;
client.tell({ kind: 'event', event: [':decide', 1, 1, ':save'] });
r = await settle(await propose(mark), 'save');
assert.deepEqual([cand().verified, cand().saved, cand().live], [true, true, true]);
const inv2 = r.body.board.files[0];
assert.equal(inv2.rev, 2);
assert.equal(inv2.forms.length, 8, 'the file now holds the candidate\'s forms');
const decisionBlocks = r.body.board.streams[0].blocks.filter(b => b.kind === 'decision');
assert.deepEqual(decisionBlocks.map(b => b.rev), [1, 1, 2], 'each decision records the file revision it acted on');
const decisions = decisionBlocks.map(b => b.text);
assert.deepEqual(decisions, ['Verified · candidate v1',
  'Made Live · the workspace image runs it; the file is unchanged · candidate v1',
  'Saved source · src/app/invoices.bl rev 2 · candidate v1']);
ok('Save bumps the file to rev 2 with the candidate\'s forms; each decision is its own block');

// a stale revision: the browser still believes rev 1 until the view updates,
// so propose by hand as a tab that never saw the save
const HTTP_TAB = 'wsprobe000000001';
r = await app.post({ request: 1, revision: r.body.revision, digest, nonce: nonce(HTTP_TAB, 1), op: 'eval-form',
                     args: { stream: 0, path: 'src/app/invoices.bl', rev: 1, form: top(5).id } });
assert.equal(r.status, 422);
assert.equal(r.body.reason, 'stale-basis');
r = await app.post({ request: 2, revision: r.body.revision, digest, nonce: nonce(HTTP_TAB, 2), op: 'decide',
                     args: { stream: 1, cand: 1, step: 'save' } });
assert.equal(r.body.reason, 'already-saved');
ok('the server refuses an eval against an old revision (stale-basis) and a second Save (already-saved)');

const rev1Receipts = r.body.board.direct.filter(b => b.rev === 1).length;
assert.ok(rev1Receipts >= 3, 'receipts from rev 1 are kept, on rev 1');
ok('receipts keep the revision they were taken on');

// ── 5. the Stream document ──────────────────────────────────────────────────
const s1 = () => r.body.board.streams[0];
await send([':edit-spec', 1], v => findAll(v.tree, n => Array.isArray(n) && n[0] === 'textarea').length === 1, 'spec editor');
await send([':spec', 'Late fees stay out of the total.'], v => texts(v.tree).includes('Draft · unsaved'), 'draft');
mark = client.frames.length;
client.tell({ kind: 'event', event: [':save-spec', 1] });
p = await propose(mark);
assert.deepEqual(p.args, { stream: 1, spec: 'Late fees stay out of the total.', basis: 1 });
r = await settle(p, 'spec');
assert.deepEqual([s1().spec, s1()['spec-rev']], ['Late fees stay out of the total.', 2]);
r = await app.post({ request: 3, revision: r.body.revision, digest, nonce: nonce(HTTP_TAB, 3), op: 'save-spec',
                     args: { stream: 1, spec: 'an older draft', basis: 1 } });
assert.equal(r.body.reason, 'stale-basis');
ok('a spec save carries the basis it was edited from; a save from an older basis is refused');

// a comment on a form, from a source pane inside the Stream
await send([':pane', 'src/app/invoices.bl'], v => findAll(v.tree, n => attr(n)?.class === 'pane').length === 1, 'pane');
const cap = find(inv2.forms, f => f.kind === 'symbol' && f.text === 'late-fee-cap');
await pick(cap.id);
await send([':comment-draft', 'Is 25 per invoice or per fee?'], v => true, 'draft comment');
mark = client.frames.length;
client.tell({ kind: 'event', event: [':send-comment', 1, ':form', 2] });
p = await propose(mark);
assert.deepEqual(p.args, { stream: 1, reply: 0, text: 'Is 25 per invoice or per fee?', path: 'src/app/invoices.bl', rev: 2, form: cap.id });
r = await settle(p, 'comment');
const c = s1().blocks.at(-1);
assert.deepEqual([c.kind, c.path, c.rev, c.form], ['comment', 'src/app/invoices.bl', 2, cap.id]);
ok('a comment from a source pane is anchored to path · rev · form');

// a turn: recorded, and no model answer invented
await send([':ask-draft', 'Should the cap apply to reminders?'], v => true, 'ask');
mark = client.frames.length;
client.tell({ kind: 'event', event: [':ask', 1] });
r = await settle(await propose(mark), 'ask');
const [task, answer] = s1().blocks.slice(-2);
assert.deepEqual([task.kind, task.text], ['task', 'Should the cap apply to reminders?']);
assert.equal(answer.failed, true);
assert.match(answer.text, /No model provider is connected/);
ok('Record turn appends the task and states that no response was invented');

// run a cell in the harness namespace
mark = client.frames.length;
client.tell({ kind: 'event', event: [':run-cell', 1, 103] });
r = await settle(await propose(mark), 'run cell');
assert.equal(s1().blocks.find(b => b.id === 103).result, '42');
ok('Run cell evaluates the cell and records its result');

// a new Stream is predicted: it shows before the server answers
await send([':new-open'], v => texts(v.tree).includes('New Stream'), 'dialog');
await send([':new-title', 'Reminder fees'], v => true, 'title');
mark = client.frames.length;
client.tell({ kind: 'event', event: [':new-stream'] });
const predicted = await awaitView(v => texts(v.tree).includes('Stream · Reminder fees'), mark, 'predicted stream');
assert.ok(texts(predicted.tree).includes('No spec yet — state an intent before choosing any file.'));
p = await propose(mark);
r = await settle(p, 'new stream');
assert.equal(r.body.board.streams.at(-1).title, 'Reminder fees');
assert.deepEqual(r.body.board.streams.at(-1).sources, [], 'a Stream starts with no file');
ok('New Stream is predicted in the browser, starts with no file and no spec, and the server agrees');

// ── 6. the palette is the one action catalogue ──────────────────────────────
await send([':palette'], v => findAll(v.tree, n => attr(n)?.role === 'dialog').length === 1, 'palette');
const actionLabels = () => findAll(lastView().tree, n => Array.isArray(n) && attr(n)?.class === 'action')
  .map(n => textOf(n[2]));
const labels = actionLabels();
for (const l of ['Switch to Source', 'Open Activity', 'New Stream', 'Open source src/billing/rules.bl'])
  assert.ok(labels.includes(l), 'the palette offers ' + l);
await send([':q', 'rules'], v => true, 'filter');
const filtered = actionLabels();
assert.ok(filtered.length >= 1 && filtered.every(l => /rules/i.test(l)), 'the filter keeps only matching actions');
assert.equal(Object.keys(keysOf(lastView().tree)).length, 0, 'while the palette is open no view key is bound');
ok('the palette lists every action by name, filters, and owns the keyboard while open');

await client.close();
await app.close();

// ── 7. an authority that does not answer in time fails closed, and ANSWERS ──
// A timed-out intent used to be removed from the waiters before the service
// failed, so its HTTP request was never answered and the client hung. Every
// commit takes far longer than 1 ms, so the first one times out. One BL
// runtime per process (split-test-kit.mjs), so this server is a child.
const slowSource = `
  import { startApp, nonce } from './split-test-kit.mjs';
  const slow = await startApp('workspace', { authorityTimeoutMs: 1 });
  const s0 = await slow.snapshotNow();
  const post = (n, op, args) => slow.post({ request: n, revision: s0.revision, digest: ${JSON.stringify(digest)},
                                            nonce: nonce('wsslow0000000001', n), op, args });
  const t0 = Date.now();
  const a = await post(1, 'eval-form', { stream: 0, path: 'src/app/invoices.bl', rev: 1, form: s0.board.files[0].forms[5].id });
  const ms = Date.now() - t0;
  const b = await post(2, 'ask', { stream: 1, text: 'still there?' });
  process.stdout.write(JSON.stringify({ a: [a.status, a.body.reason], ms, b: [b.status, b.body.reason] }));
  await slow.close();
  process.exit(0);`;
const { spawn } = await import('node:child_process');
const slowRun = await new Promise((resolve, reject) => {
  const child = spawn(process.execPath, ['--input-type=module', '-e', slowSource],
                      { cwd: new URL('./', import.meta.url).pathname, stdio: ['ignore', 'pipe', 'ignore'] });
  let out = '';
  child.stdout.on('data', d => { out += d; });
  const kill = setTimeout(() => { child.kill('SIGKILL'); reject(new Error('the timed-out request was left hanging')); }, 30000);
  child.on('exit', () => { clearTimeout(kill); try { resolve(JSON.parse(out)); } catch { reject(new Error('no answer: ' + out)); } });
});
assert.deepEqual(slowRun.a, [503, 'authority-unavailable']);
assert.ok(slowRun.ms < 5000, 'answered promptly, not left hanging');
assert.deepEqual(slowRun.b, [503, 'authority-unavailable'], 'and stays closed');
ok('a timed-out authority answers 503 at once and stays failed closed, instead of leaving the request hanging');

console.log(`js-actors: WORKSPACE PASS (${passed} checks)`);
