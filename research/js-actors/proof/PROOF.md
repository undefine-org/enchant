# Proof log — the split showcase, track by track

Start everything: `node research/js-actors/showcase-all.mjs --base 8801`, then
open http://127.0.0.1:8801/ (gallery, `gallery.png`). Seven apps, one per
capability; each entry below says what was claimed, how it was checked, and
what was observed — including what was found broken along the way.

Each entry says what was claimed, how it was checked, and the observed result.
Commands run from the repository root with
`BEAM_LISP_Z3=/usr/bin/z3 ELIXIR_ERL_OPTIONS='+S 8:8 +SDio 8'`. Screenshots are
real browser captures of `node research/js-actors/split-server.mjs`.

## Track 1 — higher-order client code (PLAN-149)

**Claim.** Client code may create, store, compose and call function values
(`comp`, `partial`, `juxt`, `complement`, `constantly`, `apply`, lambdas that
return lambdas, predicates folded into one), and recurse over data, while every
admitted client call chain provably terminates.

**Mechanism.** `compiler.bl` "function values: closure flow": 0-CFA over the
app's ANF with a runtime model derived from `runtime.bl`; every call cycle must
pass *capture order* or *structural descent* (README, "Client code is higher
order"). Supporting soundness fixes, each with native tests:

| Commit | Fix | Test |
|---|---|---|
| `9417427e` | a loop bound must be loop-INVARIANT (`(let [n (count xs)] (if (< i n) (recur (inc i) (conj xs 1))))` was accepted) | `termination_anf_test` `a-bound-must-be-loop-invariant` |
| `6e9de4d2` | `rest`/`next` shrink only under a non-empty guard (`(loop [s [1]] (recur (rest s)))` was accepted; confirmed to run forever on BEAM) | `a-sequence-step-needs-a-non-empty-guard` |
| `a77a356a` | footprints are the LEAST fixpoint (a recursive fn was opaque by its own first guess) | `analyze_test` `recursion-converges-to-its-real-effects` |

**Checks.**

| Check | Result |
|---|---|
| full build `./bin/bl run research/js-actors/compiler.bl` | exit 0, 53 OK diagnostics, PORTABLE HELPER PASS |
| split fixtures (`JS_ACTORS_SPLIT_ONLY=1`) | `SPLIT PASS placement derived, 13 refusals named, 4 higher-order fixtures admitted` — refused: omega, Y-combinator-style knot through `comp`, mutual recursion, recursion rebuilding its input, number recursion, effects in created lambdas; admitted: rank-two lambda, computing value, `juxt`/`comp`/`partial`/`complement`/`apply`, recursive tree walk |
| `node research/js-actors/verify-split.mjs` | `SPLIT PASS (23 checks)` incl. refine chips (open / open∧long / long / none) computed in the client with no proposal |
| `node research/js-actors/verify-order-parity.mjs` | `ORDER PARITY PASS (29 answers identical to BEAM)` — 11 new combinator/prelude cases (30 after the main merge: + sequential family) |
| all 20 Node suites (`verify.mjs` + `verify-*.mjs`) | 20/20 pass |
| native suites | termination 26, analyze 50, footprint-anf 28, explain 41, native-eligible 11, incremental 11, check 49, prove 13, lsp 59, lsp-position 531, lsp-cli 8, growth 15, rewrite 52, smt 7+5+15+8+17 |
| independent probe of the gate (a separate agent, ~90 programs in 13 categories: capture through data/HOF/loops/rest lists; first/rest/lookup/guard/rebinding/swap/maps/vals/get-default attacks; runtime-model scan) | **no admitted non-terminating program**. One model gap found — `rt-spawn`/`rt-run-pid` hand functions to host leaves that call them — unreachable from client code, and closed anyway (`calling-host-leaves`) |

**Found by the differential, fixed.** `(apply f v)` with a vector raised on the
JS target (`listToArray`); `keep`/`mapcat` returned vectors where BEAM returns
seqs. **Documented divergence:** an empty lazy result is `=` nil on BEAM and
`()` here.

## Merge — main's bootstrapped runtime (`3b48176f`)

**Claim.** The JS target follows main's runtime move to `priv/boot/rt.bl`
(`BeamLisp.Ns.Rt`) with no loss.

**Checks.** The parity differential caught the two semantic changes the merge
brought — lists and vectors are one sequential family under `=`/`compare`
(map keys stay distinct), and empty `sort`/`take` are `()` — and a frontend
change (`__STACKTRACE_RAW__` bound around catch bodies) broke 11 Node suites
until the JS catch block bound it. After the fixes: build exit 0, 53 OK, SPLIT
PASS, PORTABLE HELPER PASS, 20/20 Node suites, `ORDER PARITY PASS (30 answers)`
with a new `sequential-family` case.

## Track 2 — recursion over data (PLAN-149)

**Claim.** An app may declare a recursive snapshot type and walk it with
ordinary recursion in both halves; every admitted walk terminates, the wire
stays bounded, and the app is a real product: a nested project plan.

**App.** `apps/outline.bl` — phases → tasks → steps. Progress roll-ups
(`tally`), search that keeps the ancestors of a match and highlights it
(`prune`, `marked-text`), fold/expand and inline "+ step" run in the browser
with no network; add, tick (the whole branch at once) and remove go to the
server, which rebuilds the path to one item.

| Check | Result |
|---|---|
| split build (`JS_ACTORS_SPLIT_ONLY=1`) | `SPLIT PASS outline: 14 placements, 12 recursion proofs, 5 refusals named` (walk on itself, re-wrapped item, growing search text, list-less recursive type, 25-deep type) |
| `node research/js-actors/verify-outline.mjs` | `OUTLINE PASS (22 checks)`: recursive contract + digest, placements and `structural` proofs, no server code in the client bundle, codec depth bound (24 ok / 25 refused, BL = JS), the bound equal in three files, HTTP adds/refusals (`no-such-item`, `too-deep`), subtree toggle both ways, subtree removal, SSE fan-out, BL client: tally text, fold with no proposal, search keeps ancestors + `em` highlight, empty search, inline add proposes and commits, toggle proposes |
| real browser, port 8792 | fold/expand, search `magic` → Build › Sign-up flow › Magic link with `Magic` highlighted; inline add focused on open, Enter commits rev 1; ticking Research ticked its 6 descendants; search-render latency 43–144 ms per keystroke. Screenshots: `track2-outline.png`, `track2-outline-search.png` |
| **found in the browser, fixed** | while searching, roll-ups counted only the matching branches ("Build 0/2"); they now count the whole branch (`Build 1/5`) |
| independent red-team (a separate agent, ~60 programs: lookups of call results, map-as-fn, keyword in a local, `get-in`, defaults, mutual :part/:le cycles, arity mixes, loops in cycles, case patterns) | **no admitted non-terminating program**. Soundness of ":part counts as :le": every read `sub-rel` recognizes returns a subterm or nil; anything that can grow (`conj`/`assoc`/`cons`/`into`/literals/`str`) carries no relation and refuses the edge. Found and FIXED: a non-recursive type nested past the bound was admitted though no value could pass (now refused); `(nth coll i default)` was read as a lookup (only 1–2 argument reads count now). Reported and REJECTED on inspection: "a `case` symbol pattern is read as a binder". The compiled ANF shows `(case (conj it []) it (cand it) 0)` tests equality against the LOCAL `it` (`{:op :var :name "it_…"}`) — no binding happens, and `(cand it)` recurses on an element, which is genuinely structural |
| full build + all Node suites | build exit 0, 53 OK, SPLIT PASS (showcase + outline), PORTABLE HELPER PASS, parity 30, 22/22 Node suites |

## Track 3 — instant edits, confirmed by the server; offline (PLAN-149)

**Claim.** An edit shows in the same frame as the click; the server's answer
confirms or reverts it; a server that decides differently wins visibly; edits
made offline are kept, shown, and sent in order when the link returns; a
resend never applies twice.

**Mechanism.** `split-client.bl` rewritten around a queue (one in flight,
oldest first; re-checked against the confirmed board before sending);
`:predict`/`:agrees?` per intent (client roots, gated like the view); a nonce
per proposal, committed at most once by `split-server.bl` (last 256);
`offline`/`online` inputs. App: `apps/groceries.bl`; the outline also predicts
ticks and removals now (a whole branch ticks at once). New wire type
`[:one-of k …]`.

| Check | Result |
|---|---|
| split build | `SPLIT PASS groceries: 11 placements, 3 refusals named` (a prediction with an effect, a prediction of the wrong arity, a malformed enum) |
| `verify-groceries.mjs` | `GROCERIES PASS (22 checks)`: enum codec; placement; tick committed once, same nonce → `duplicate`, revision unchanged; server merge of a duplicate name; instant tick before any answer; queue order with auto-drain; slide-back after another tab won (`already-so`, `no-such-item`); divergence reported on a merge; a new row predicted right is NOT reported; offline: 3 edits shown and queued, "Offline · 3 changes waiting", drained in order on online |
| `verify-split.mjs` (migrated onto the shared kit) | `SPLIT PASS (28 checks)`: unanswered intent stays queued, resent with the same nonce on online, committed once, re-post answered `duplicate` |
| `verify-outline.mjs` | `OUTLINE PASS (22 checks)`: a tick shows the whole branch done before any answer |
| real browser, port 8794 | click → predicted render **42 ms**, confirmed **114 ms** (row marked saving between); offline: 3 edits shown with "waiting", header "Offline · 3 changes waiting"; online: all three committed in order in 383 ms; "Oat milk" added again → one row, qty 3, note "The server adjusted that…"; tick raced by another tab → "Not applied — someone already did that.", row shows the other tab's state. Screenshots `track3-groceries-offline.png`, `track3-groceries-race.png` |
| **found in the browser, fixed** | adding a NEW item was reported as diverged (the prediction's provisional id 0 ≠ the server's id) → `:agrees?`; raw reason keywords in notes → words; `rest` of a vector raised on the JS target (the queue is a vector) → `rt-rest` takes vectors, parity case `rest-of-vectors` (31 answers) |

## Tracks 4 and 5 — who and when: identity, permissions, durable history (PLAN-149)

**Claim.** People sign in; the transport verifies a session and stamps the
person on every proposal; permissions are BL decided on the server (and
mirrored in the view); presence is live; every commit is written to a durable
log replayed at boot; the activity feed, shared undo/redo and "view as of" come
from the authority.

**Mechanism.** `split-server.bl` rewritten (`:people`, `:allow`, `:apply` with
the person, `:says`, `:history`, built-in `:undo`/`:redo` with `:undo-allow`,
login/presence/peek topics, a `commit` emit per commit). Transport:
`split-session.mjs` (HMAC-signed session ids, strict cookie parsing, log line
validation), `split-server.mjs` (`/api/login|logout|me|peek`, stamping, SSE
presence, append-before-answer log, fail-closed replay). Client shell: `sync`
gains `:me :people :online :recent :history :asof`. App: `apps/team.bl`.

| Check | Result |
|---|---|
| split build | `SPLIT PASS team: 15 placements, 3 refusals named` (declaring `:undo` in a history app, a roster made `:private` while the view needs names, `:allow` of the wrong arity) |
| `verify-session.mjs` | `SESSION PASS (20 checks)`: sign/verify, tampered sid/MAC/secret refused (timingSafeEqual), exact cookie attributes, log parse incl. torn last line and bad middle line |
| `verify-team.mjs` | `TEAM PASS (31 checks)`: contract; placement (permissions server-only in the bundle); cookie `HttpOnly; SameSite=Strict; Path=/; Max-Age=43200`; tampered cookie → signed out; logout; the full permission matrix (guest 401, viewer, member own/others', lead); a proposal carrying `actor` → 400; entry author = session user; feed in the server's words; undo/redo summaries, future cleared by a new commit; presence {Ana, Chloé} without duplicates, updated on close; peek = board at k; log has one line per commit; a second boot replays 8 commits to an identical board/feed/history and still refuses a resent nonce as duplicate; torn last line tolerated (file truncated byte-identical); bad middle line → boot fails naming line 2; BL client offers only permitted buttons per person, read-only past board refuses edits |
| real browser, port 8795 | guest: no composer, no move buttons; Ben: moves only his cards, feed "Ben moved “Fix flaky login test” to In progress"; Ana (lead) with Chloé connected in another session: "here now" shows A and C; assign → undo ("Unassigned") → redo ("Chloé"); scrubber to rev 1: 6 cards, read-only banner, an edit refused "you're looking at the past"; **server killed with SIGKILL and restarted**: `SPLIT REPLAYED 5 commits`, page shows rev 5, same 7 cards, 5 feed entries, Chloé still assigned. Screenshots `track4-team-lead.png`, `track5-team-history.png` |
| **found in the browser, fixed** | a view tag the page does not render printed "[object Object]" (`:b` in the feed) → the renderer reports it; the page module had a misplaced `else` that only a browser import would catch → `verify-shell` now parses every page/Worker module |

**Limits.** Demo roster, no passwords; sessions are per server process (a
restart signs people out, the board survives); the log is one file per app,
appended synchronously.

## Track 6 — interaction as data (PLAN-149)

**Claim.** Keyboard-first use, drag-and-drop and inline editing work in a
real browser, declared by the BL view as data; reorder is a predicted,
server-confirmed intent.

| Check | Result |
|---|---|
| split build | `SPLIT PASS triage: 9 placements, 2 refusals named` (a key bound to `:private` data, a key binding with an effect) |
| `verify-triage.mjs` | `TRIAGE PASS (18 checks)`: move-before up and down over HTTP, `same-place`/`no-such-report`; the view's `:keys` map exactly j k ↑ ↓ ? h x e ⏎ p; selection moves with `focused`; editing empties the keymap; save proposes, cancel does not; drop proposes and the next view predicts the new order; a non-numeric drag key is refused locally; unoffered events do nothing; the echo guard |
| real browser, port 8796 (real key presses) | `j` `j` `x` → third report selected, focused, fixed (rev 1); `e` → inline field focused with the title; typed + ⏎ → renamed (rev 2), focus back on the row; drag r7 onto r1 → predicted order in **49 ms**, confirmed; `?` → shortcut sheet. Screenshot `track6-triage.png` |
| **found in the browser, fixed** | fast typing lost characters ("Anfications"): the Worker's renders echo older values into the focused field → echo guard in `patch()`; a render removing a focused field fired its `:on-blur` (a second save) → blurs during a render are not user blurs; the history bar showed on apps without history (`display:flex` beat `hidden`) |
| full build + all Node suites | build exit 0, 53 OK, SPLIT PASS ×5, parity 32 (+ `drop`), **26/26** Node suites |

## Track 7 — exact numbers and BEAM-ordered maps and sets (PLAN-149)

**Claim.** Integers are exact at any size on the JS target; maps and sets
enumerate in the BEAM's order wherever that order is determined; the ledger app
computes money beyond 2^53 in the browser to the cent.

**Mechanism.** `host.mjs`: one `arith` that promotes safe `Number` ↔ `BigInt`
and normalizes back (add/sub/mul/quot/rem/mod; float contagion; `/` is float
division); `hashKey`/`eq`/`compare`/printing handle BigInt; ONE key order
(`keyOrder`) used by `mapKeys` and sets — derived from BEAM probes: number <
atom < tuple < map (BL vectors) < () < list < string, integers before floats.
A set value (`BSet`) with literal, conj/disj/contains?/count/seq/into/=/print.
`compiler.bl`: unsafe literals emit as BigInt (`…n`); the `:exact` wire type;
`entry` reserved (it is the bundle's start symbol — an app `entry` defn
silently replaced it; found by the ledger, now refused by name).

| Check | Result |
|---|---|
| `verify-order-parity.mjs` | `ORDER PARITY PASS (95 answers identical to BEAM)` — +59 exact-integer/map-order/set cases, + big literals |
| `verify-numeric-exact.mjs` | `EXACT PASS (37 checks)` — Number↔BigInt normalization, hashKey equality, compare across the boundary |
| split build | `SPLIT PASS ledger: 11 placements, 2 refusals named` (`entry` reserved, `:exact` as an app type name) |
| `verify-ledger.mjs` | `LEDGER PASS (6 checks)`: `:exact` round-trips digit for digit and refuses unsafe JSON numbers/fractions/padded digits; an amount of 1 234 567 890 123 456 789 cents commits over HTTP exactly; the BL client shows balance **12 435 750 893 785 710.85** where a double sum gives 1243575089378571000; typed amounts parse to exact cents; three decimals refused locally |
| real browser, port 8797 | same balance and treasury row (90 071 992 547 409.93) rendered; typing 12345678901234567.89 → "you typed 12 345 678 901 234 567.89", added (rev 1), balance exact; breakdown bars from exact integer ratios. Screenshot `track7-ledger.png` |

**Divergences, stated.** Keyword-keyed maps: BEAM orders atoms by atom-table
index (creation order: `{:b :a :c}` keys come out `(:c :a :b)`), which no
browser can know; the JS target orders keywords by name, and parity pins only
cases whose order is determined. Maps over 32 keys: BEAM uses hash order; the
JS target keeps term order. `1` and `1.0` are one JS Number (`(/ 8 2)` prints
`4`, BEAM `4.0`). Decimals are not implemented.
| full build + all Node suites | build exit 0 (52 OK diagnostics: the "unsafe literal refused" diagnostic became a positive exact-emission test), SPLIT PASS ×6, parity 95, **28/28** Node suites |

## Generative editor mockup — Source and Stream (`apps/workspace.bl`)

**Claim.** The direction in [docs/design/workspace-editor.md](../../../docs/design/workspace-editor.md),
[stream-workspace.md](../../../docs/design/stream-workspace.md) and
[form-first-interaction.md](../../../docs/design/form-first-interaction.md) can be
mocked up *functionally* as one split BL app, in the playground's Carbon (dark)
and Snow (light) tokens (`research/workspace-spike/play/ui.css`, copied
verbatim). The pieces the design depends on are real, not drawn:

| Real | Mock (and labelled as one in the UI) |
|---|---|
| the form tree: the server reads each file with a small BL reader into forms with stable ids; the browser renders code from it and selects forms, never characters | the runtime: integers, strings, keywords, vectors, maps, 13 builtins and top-level `def`s; calling a `defn` says it is outside the mock |
| the motion contract (`j`/`k`/`h`/`l` ≐ Ctrl+J/K/H/L), computed in the browser by `motion` | the model: **Record turn** appends the task and a block saying no response was invented |
| `Evaluate form` → an intent naming path · rev · form, refused if stale in the browser AND on the server; the receipt goes to the open Stream (source pane) or the file's own Activity | typing into source (Edit mode), hover preview, history lens: not in this mockup |
| Made / Verified / Saved / Live: four decisions, each its own block; Save is basis-guarded and bumps the file's revision; Live changes what evaluation sees without writing the file | |

| Check | Result |
|---|---|
| split build `JS_ACTORS_APP=workspace` | `SPLIT PASS workspace: 22 placements, 6 recursion proofs, 2 refusals named` — refused: a view that calls the server-private runtime `ev`; a form walk recursing on itself instead of a child |
| `node research/js-actors/verify-workspace.mjs` | `WORKSPACE PASS (21 checks)`: placement (no reader, runtime or candidate source in the client bundle or on the wire); every row of the motion table incl. both climb rules and deepest descent; the four boundary cues with no wrap; Escape unbinds motion and eval; eval → 60 with a receipt on path/rev/form; the newest receipt wins across Streams; an unbound symbol is an error receipt; Save before Verify refused locally, never sent; Verify's checks; Live → the same form evaluates to 96, file still rev 1; Save → rev 2 with the candidate's forms, decisions record rev 1, 1, 2; stale eval and double Save refused by the server; spec save from an older basis refused; a pane comment anchored to path · rev · form; Run cell; New Stream predicted with no file and no spec; palette filters and owns the keyboard; a timed-out authority answers 503 instead of hanging |
| verifier mutation checks | changing the boundary cue `Last form` in the built client fails the motion check; replacing "newest receipt" with "last in list" fails the receipt check |
| real browser, port 8811 | the four screenshots below; refusals probed over HTTP: `stale-basis`, `no-form-selected`, `no-such-file`, `already-saved`, spec `stale-basis`, bad step / extra arg → `malformed-args`, unknown op → `unknown-intent` |

Screenshots: `workspace-carbon-source.png` (a nested `(if …)` selected, its
inspector, a receipt inline), `workspace-carbon-stream.png` (a Stream with a
source pane opened from a form-anchored comment, the image running candidate
v1), `workspace-snow-activity.png` (Source Activity grouped by owner, earlier
revisions labelled), `workspace-snow-palette.png` (Search actions filtered to
the four motions and their keys).

**Found while building it, fixed in the shared target:**

| Finding | Fix | Test |
|---|---|---|
| `(assoc v i x)` on a **vector** turned it into a map on the JS target (BEAM updates the index); `update`, `assoc-in`, `update-in` and the variadic form all went the same way | `rt-assoc` writes a vector index through a new `vec-set` host leaf (bounds as on BEAM); every assoc route goes through it | `verify-order-parity`: +7 cases (`vec-assoc*`, `vec-update*`), **102 answers identical to BEAM** |
| a UI event with four items (the Worker's documented maximum) was refused as "exceeds transport bounds": the node budget did not count the event vector itself | the Worker's budget is items + 1, one constant | `verify-workspace` sends 4-item decide events |
| a snapshot failing its wire type at boot said only "does not satisfy the snapshot type" | `wire-problem` names the first failing path (`.direct[0].form does not satisfy int`) | (diagnostic only) |
| Enter on a focused button also fired a view-level `Enter` key | page keymap ignores Enter/Space on a focused button | real browser |
| **an intent that timed out left its HTTP request hanging forever**: the timer removed the waiter before failing the service, so the fail-closed path never answered it (seen as a 300 s client timeout) | the timer only fails the service; `fail` rejects every waiter, which answers 503 at once; the authority timeout is a `startSplitServer` option | `verify-workspace`: a 1 ms authority answers 503 promptly and stays closed; with the old code the check reports "left hanging" |
| two verifier races that a loaded machine exposed: `verify-split` read the render right after a result, which can still be the submit's own; `verify-triage` waited a fixed 60 ms for a render | wait for the render that shows the answer / for the render itself | 10/10 and 6/6 reruns under load |
| each commit projected the board to the wire twice more than needed | `split-server.bl` threads the projected board through its loop; a commit projects once | all apps' verifiers |

**Measured, not fixed.** A commit on this app costs ~0.8 s of CPU on the JS
authority: projecting and type-checking the whole board (~670 wire nodes) is
~125 000 trampoline steps at ~2.7 µs each. On a loaded machine that passes
the 4 s authority limit, so `verify-workspace` runs its authority with a 60 s
limit and asserts content, not latency. The cost is in the generic step
machinery, not in any one wire function.

After the fixes: the full build is exit 0 with every app's split tests, and
all 30 Node suites pass (workspace 21, parity 102, split 28, triage 18,
outline 22, groceries 22, team 31, ledger 6, shell 6, …).

## Independent security review (after tracks 4–7)

A separate reviewer red-teamed sessions, stamping, the log, the codec, the page
and the Worker. **Verified to hold** (source-traced): HttpOnly/SameSite=Strict
cookies; HMAC-SHA256 checked with timingSafeEqual; expiry and logout; the actor
is the transport's even when sent through JSON keys, headers, nested args or
prototype keys; permissions decided in BL; Host/Origin checks on login, logout
and intents; codec bounds (depth, text, lists, `:exact` digits, `:one-of`);
newline-safe JSONL; replay re-checks shape, revision and permission; text-only
rendering through an attribute allowlist; page hints and drag keys are text;
logs and BL sources are never served.

**Two defects found, both fixed and pinned by tests:**

| Finding | Fix | Test |
|---|---|---|
| a failed log append could still let the HTTP result through (result and snapshot were delivered before the append) | a durable app's ok result and snapshot are HELD until the commit is on disk; a failed append fails the service closed and the held answer is never sent | `verify-durable-ack.mjs`: the log path becomes a directory → 503, and every later intent 503 |
| an intent named with `?` (admitted by the compiler) wrote log lines the replay refused, so the app could not restart | the log's op-name rule is exactly the compiler's `[a-z][a-z0-9?-]{0,31}` | `verify-session.mjs`: `ready?` replays; `under_score`, 33 characters, `?lead` refused |

**Stated limits the review confirmed:** the Worker checks an event's handler
NAME against the last view (not the whole vector); keys outside the page's
allowlist are ignored by the page only; actors in the on-disk log are trusted
at replay (the file is the server's own); any visitor may peek at kept
revisions; a person stays "here" until their last stream closes; the 32-stream
cap can be exhausted by one client (loopback demo).

Node suites after the fixes: **29/29**.
