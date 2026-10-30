// test/js/leaves.test.mjs — the leaf table is ONE table: every key has one
// owner, and the table refuses a second definition (PLAN-163 structural fix 2).
// Run: node --test test/js/
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as R from "../../priv/lib/js/rt.mjs";
import { ERLANG, IO, bindOutput } from "../../priv/lib/js/host-leaves.mjs";

const dir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../priv/lib/js");

test("the leaf table loads (no key is defined twice)", async () => {
  const L = await import(path.join(dir, "leaves.mjs"));
  assert.ok(L.NAMES.length > 300, "expected the full table, got " + L.NAMES.length);
  assert.equal(new Set(L.NAMES).size, L.NAMES.length);
});

// The load check above only sees keys that reach the table. A static scan
// catches a duplicate the table would never get to see (a key repeated
// inside one object literal: JS keeps the LAST silently).
test("no leaf key is spelled twice in the leaf sources", () => {
  const seen = new Map();
  const dups = [];
  for (const f of ["leaves.mjs", "host-leaves.mjs", "lazy.mjs"]) {
    const src = fs.readFileSync(path.join(dir, f), "utf8");
    const lines = src.split("\n");
    lines.forEach((line, i) => {
      const m = line.match(/^\s*(?:\[LS \+ )?"([^"]+\/\d+)"\]?\s*:/);
      if (!m) return;
      const key = line.includes("[LS + ") ? "Elixir.BeamLisp.LazySeq/" + m[1] : m[1];
      if (seen.has(key)) dups.push(key + " at " + seen.get(key) + " and " + f + ":" + (i + 1));
      else seen.set(key, f + ":" + (i + 1));
    });
  }
  assert.deepEqual(dups, []);
});

// ─── erlang/bnot: exact integer complement (PLAN-163 R3) ─────────────────────
// The regression: JS `~` coerces a Number to signed 32 bits, so `(bnot
// 4294967296)` answered -1 instead of -4294967297. The leaf complements in
// BigInt and lets R.add normalize, matching the BEAM's arbitrary-precision
// integers over rt's one safe/BigInt model.
const bnot = ERLANG["erlang/bnot/1"];

test("bnot: exact complement across the 32- and 53-bit boundaries", () => {
  assert.equal(bnot(0), -1);
  assert.equal(bnot(5), -6);
  assert.equal(bnot(-1), 0);
  // 32-bit boundaries must not wrap.
  assert.equal(bnot(2147483647), -2147483648);
  assert.equal(bnot(2147483648), -2147483649);
  assert.equal(bnot(4294967295), -4294967296);
  assert.equal(bnot(4294967296), -4294967297); // was -1 without the fix
  assert.equal(bnot(-4294967296), 4294967295);
});

test("bnot: promotes past the safe-integer limit and normalizes back", () => {
  const MAXI = Number.MAX_SAFE_INTEGER; // 9007199254740991
  // A Number operand whose complement crosses the safe limit must promote …
  assert.equal(typeof bnot(MAXI), "bigint");
  assert.equal(bnot(MAXI), BigInt(-(MAXI + 1))); // -(2^53)
  // … and a BigInt operand whose complement fits must fall back to a Number.
  assert.equal(bnot(BigInt(-(MAXI + 1))), MAXI);
  assert.equal(typeof bnot(BigInt(-(MAXI + 1))), "number");
  // The negative boundary's complement is still a Number.
  assert.equal(bnot(Number.MIN_SAFE_INTEGER), MAXI - 1);
  // BigInt beyond the safe range keeps exact precision (no 32-bit truncation).
  assert.equal(bnot(9007199254740993n), -9007199254740994n);
  assert.equal(typeof bnot(9007199254740993n), "bigint");
});

test("bnot: rejects every non-integer with the Erlang-shaped badarg", () => {
  const isBadarg = (e) => e instanceof R.BLError && e.blType === R.kw("Elixir.ArgumentError");
  // floats stay distinct values (even whole), as do exact decimals; a
  // non-integer Number, a string, nil, booleans, keywords and lists are not
  // integers on the BEAM either.
  const invalid = [1.5, R.flt(5), R.flt(5.5), R.dec(5n, 0), "5", null, true, false, R.kw("a"), R.EMPTY];
  invalid.forEach((x, i) => assert.throws(() => bnot(x), isBadarg, "invalid operand #" + i));
});
// ─── lists/reverse: ONE exact reverse, arbitrary shared tail (PLAN-163) ──────
// `lists:reverse/2` reverses a PROPER first list onto an arbitrary tail and
// never forces it; `/1` is `/2` with the empty tail. `R.reverseI` is the one
// helper the emitter intrinsic and the `LEAVES` dispatch both call, so their
// values and their badarg cannot disagree.
const L = await import(path.join(dir, "leaves.mjs"));
const Z = await import(path.join(dir, "lazy.mjs"));
const xs = (l) => { const a = []; for (let p = l; p instanceof R.Cons; p = p.t) a.push(p.h); return a; };
const isBadarg = (e) => e instanceof R.BLError && e.blType === R.kw("Elixir.ArgumentError");

test("reverse/1: a proper list reverses, order and value exact", () => {
  assert.deepEqual(xs(R.reverseI(R.EMPTY)), []);
  assert.deepEqual(xs(R.reverseI(R.list(1, 2, 3))), [3, 2, 1]);
  assert.equal(R.reverseI(R.list(1, 2, 3)).n, 3);          // proper list
  assert.deepEqual(xs(R.reverseI(R.list("a", R.kw("b"), 3))), [3, R.kw("b"), "a"]);
  // the leaf is the intrinsic at arity 1
  assert.deepEqual(xs(L.LEAVES["lists/reverse/1"](R.list(1, 2, 3))), [3, 2, 1]);
});

test("reverse/2: the tail is shared and never forced; `/1` tails ()", () => {
  let forced = 0;
  const tail = Z.newLazy(() => { forced++; return R.list(9); });
  const r = R.reverseI(R.list(1, 2, 3), tail);
  assert.deepEqual(xs(r), [3, 2, 1]);
  assert.equal(r.t.t.t, tail);            // EXACT identity, not a copy
  assert.equal(r.n, -1);                  // improper: a lazy tail
  assert.equal(forced, 0);                // never forced
  assert.deepEqual(xs(R.reverseI(R.list(1, 2))), [2, 1]); // default tail
  const s = R.reverseI(R.list(1, 2), R.kw("end"));        // scalar tail allowed
  assert.deepEqual(xs(s), [2, 1]);
  assert.equal(s.t.t, R.kw("end"));
});

test("reverse/2: an empty first list returns the tail EXACTLY, unforced", () => {
  let forced = 0;
  const tail = Z.newLazy(() => { forced++; return R.list(1); });
  assert.equal(R.reverseI(R.EMPTY, tail), tail);
  assert.equal(R.reverseI(R.EMPTY, 42), 42);
  assert.equal(R.reverseI(R.EMPTY, R.kw("any")), R.kw("any"));
  assert.equal(forced, 0);
});

test("reverse: null/non-list/improper first arg is the Erlang-shaped badarg", () => {
  const improper = [new R.Cons(1, 2), new R.Cons(1, new R.Cons(2, 3)),
                    new R.Cons(1, Z.newLazy(() => R.list()))];
  const bad = [null, 5, "s", R.kw("k"), R.tup([1]), R.flt(1), ...improper];
  bad.forEach((x, i) => assert.throws(() => R.reverseI(x), isBadarg, "invalid/1 #" + i));
  bad.forEach((x, i) => assert.throws(() => R.reverseI(x, R.EMPTY), isBadarg, "invalid/2 #" + i));
});

test("reverse: the intrinsic and the LEAVES dispatch agree", () => {
  const l1 = L.LEAVES["lists/reverse/1"], l2 = L.LEAVES["lists/reverse/2"];
  const src = R.list(1, 2, 3), tail = R.list(9);
  assert.deepEqual(xs(l1(src)), xs(R.reverseI(src)));
  const a = l2(src, tail), b = R.reverseI(src, tail);
  assert.deepEqual(xs(a), xs(b));
  assert.equal(a.t.t.t, tail);
  assert.equal(b.t.t.t, tail);
  assert.throws(() => l1(new R.Cons(1, 2)), isBadarg);
  assert.throws(() => l2(new R.Cons(1, 2), tail), isBadarg);
});


test("Enumerable input cells use host map entries and graphemes", async () => {
  const Z = await import("../../priv/lib/js/lazy.mjs");
  const entry = Z.cell(R.EMPTY_MAP.assoc(R.kw("doc"), "doc"));
  assert.ok(entry instanceof R.Cons);
  assert.ok(entry.h instanceof R.Tup);
  assert.deepEqual(entry.h.items, [R.kw("doc"), "doc"]);
  assert.strictEqual(Z.cell(R.EMPTY_MAP), null);
  const chars = Z.toList("e\u0301👍🏽");
  assert.equal(chars.n, 2);
  assert.deepEqual([chars.h, chars.t.h], ["e\u0301", "👍🏽"]);
});

test("shared printer output writes exact Unicode text and returns ok", () => {
  const writes = [];
  bindOutput(text => writes.push(text));
  try {
    assert.strictEqual(IO["io/format/2"]("~ts~n", R.list("é🙂\nsecond")), R.kw("ok"));
    assert.strictEqual(IO["io/format/2"]("~ts", R.list("tail")), R.kw("ok"));
    assert.strictEqual(IO["io/format/2"]("~ts~n", R.list("")), R.kw("ok"));
    assert.deepEqual(writes, ["é🙂\nsecond\n", "tail", "\n"]);
  } finally { bindOutput(null); }
});

test("output validates its arguments before writing and names unsupported formats", () => {
  const writes = [];
  bindOutput(text => writes.push(text));
  try {
    for (const args of [R.EMPTY, R.list("x", "y"), R.consRaw("x", null), R.list(1)])
      assert.throws(() => IO["io/format/2"]("~ts~n", args), e => e.blType === R.kw("Elixir.ArgumentError"));
    assert.throws(() => IO["io/format/2"]("~p", R.list(1)), /io\/format supports/);
    assert.deepEqual(writes, []);
  } finally { bindOutput(null); }
});

test("output propagates sink errors without substituting another printer", () => {
  const error = new Error("closed sink");
  bindOutput(() => { throw error; });
  try { assert.throws(() => IO["io/format/2"]("~ts~n", R.list("x")), e => e === error); }
  finally { bindOutput(null); }
});


test("String segmentation fast paths preserve CRLF and Unicode grapheme slicing", async () => {
  const {STRING} = await import("../../priv/lib/js/host-leaves.mjs");
  const slice = STRING["Elixir.String/slice/3"], length = STRING["Elixir.String/length/1"];
  for (const text of ["ASCII", "a\r\nb", "e\u0301👍🏽z", "🇫🇷👨‍👩‍👧‍👦x"]) {
    const gs = Array.from(new Intl.Segmenter(undefined, {granularity:"grapheme"}).segment(text), x => x.segment);
    assert.equal(length(text), gs.length);
    for (let start=-gs.length;start<=gs.length;start++) for(let n=0;n<=gs.length;n++) {
      assert.equal(slice(text,start,n),gs.slice(start,start+n).join(""));
      assert.equal(slice(text,start,n),gs.slice(start,start+n).join(""));
    }
  }
  for(let i=0;i<300;i++) length("e\u0301"+i);
  assert.equal(slice("e\u0301👍🏽z",0,2),"e\u0301👍🏽");
});

test("reversing Unicode cannot mutate cached segmentation", async () => {
  const {STRING,REGEX} = await import("../../priv/lib/js/host-leaves.mjs");
  const s="a💧é";
  assert.equal(REGEX["Elixir.String/reverse/1"](s),"é💧a");
  assert.equal(REGEX["Elixir.String/reverse/1"](s),"é💧a");
  assert.equal(STRING["Elixir.String/slice/3"](s,0,2),"a💧");
});

// Core get-in uses a fresh opaque sentinel; missing this leaf makes every
// canonical browser build fail, even if the app never calls get-in directly.
test("make_ref: unique immutable identities survive map/set lookup", () => {
  const make = ERLANG["erlang/make_ref/0"], isRef = ERLANG["erlang/is_reference/1"];
  const a = make(), b = make();
  assert.ok(isRef(a)); assert.ok(isRef(b)); assert.ok(Object.isFrozen(a));
  for (const value of [null, {}, {blRef:true}, R.hashMap(), "ref", () => {}]) assert.equal(isRef(value), false);
  assert.equal(R.keyEq(a,a),true); assert.equal(R.keyEq(a,b),false);
  assert.equal(R.eqv(a,a),true); assert.equal(R.eqv(a,b),false);
  assert.equal(R.hashOf(a),R.hashOf(a));
  const m = R.hashMap(a, null, b, false);
  assert.equal(m.cnt,2); assert.equal(m.get(a,"absent"),null);
  assert.equal(m.get(b,"absent"),false); assert.equal(m.get(make(),"absent"),"absent");
  assert.equal(R.hashSet(a,a,b).cnt,2);
  assert.equal(R.termCompare(a,a),0);
  assert.equal(R.termCompare(a,b),-R.termCompare(b,a));
  assert.notEqual(R.termCompare(a,b),0);
  assert.equal(R.compare(a,a),0);
  assert.equal(R.compare(a,b),-R.compare(b,a));
  assert.notEqual(R.compare(a,b),0);
  assert.equal(R.termCompare(R.kw("z"),a),-1);
  assert.equal(R.termCompare(a,() => {}),-1);
  assert.match(R.printStr(a),/^#Ref<js\.\d+>$/);
});

test("actor and synchronous reference primitives use the same runtime functions", async () => {
  const H = await import("../../priv/lib/js/actor/host.mjs");
  assert.equal(H.erlangRef("make_ref"), ERLANG["erlang/make_ref/0"]);
  assert.equal(H.erlangRef("is_reference"), ERLANG["erlang/is_reference/1"]);
  assert.equal(H.erlangRef("is_reference")(ERLANG["erlang/make_ref/0"]()),true);
  assert.equal(ERLANG["erlang/is_reference/1"](H.erlangRef("make_ref")()),true);
  assert.equal(H.erlangRef("is_reference")(R.vec(R.kw("ref"),1,2)),false);
});

const leaf = (key) => L.LEAVES[key];
const cd = (name, arity) => leaf(`Elixir.BeamLisp.CompilerData/${name}/${arity}`);
const en = (name, arity) => leaf(`Elixir.Enum/${name}/${arity}`);

test("compiler Enum adapters preserve order, truthiness, exact keys and callback exceptions", () => {
  const visited = [];
  assert.equal(en("all?", 2)(R.list(0, "", false, 9), x => { visited.push(x); return x; }), false);
  assert.deepEqual(visited, [0, "", false]);
  assert.equal(en("all?", 2)(R.EMPTY, () => { throw new Error("empty callback"); }), true);
  assert.equal(en("empty?", 1)(R.EMPTY_MAP), true);
  assert.equal(en("empty?", 1)(R.vec(1)), false);
  assert.equal(en("each", 2)(R.list(3, 1, 2), x => visited.push(x)), R.kw("ok"));
  assert.deepEqual(visited.slice(3), [3, 1, 2]);
  const failure = new Error("callback");
  assert.throws(() => en("each", 2)(R.list(1, 2), () => { throw failure; }), e => e === failure);
  let calls = 0;
  const groups = en("group_by", 2)(R.list(3, 1, 2, 4), x => { calls++; return x % 2; });
  assert.equal(calls, 4);
  assert.deepEqual(xs(groups.get(1)), [3, 1]);
  assert.deepEqual(xs(groups.get(0)), [2, 4]);
  const exact = en("group_by", 2)(R.list(1, R.flt(1)), x => x);
  assert.equal(exact.cnt, 2);
  for (const value of [null, "abc"]) assert.throws(() => en("empty?", 1)(value), /Enumerable protocol/);
});

test("Enum predicates inspect only the required lazy prefix and maps enumerate tuples", () => {
  let forced = 0;
  const tail = Z.newLazy(() => { forced++; throw new Error("tail"); });
  const prefix = new R.Cons(1, tail);
  assert.equal(en("empty?", 1)(prefix), false);
  assert.equal(en("all?", 2)(prefix, () => false), false);
  assert.equal(forced, 0);
  const values = [];
  en("each", 2)(R.hashMap(R.kw("key"), 42), x => values.push(x));
  assert.deepEqual(values[0].items, [R.kw("key"), 42]);
});

test("maps/with uses exact key identity, ignores missing/duplicate keys, refuses malformed lists", () => {
  const input = R.hashMap(1, "integer", R.flt(1), "float", "other", 3);
  const select = leaf("maps/with/2");
  const result = select(R.list(1, 1, "missing"), input);
  assert.equal(result.cnt, 1);
  assert.equal(result.get(1), "integer");
  assert.equal(result.has(R.flt(1)), false);
  assert.equal(input.cnt, 3);
  assert.throws(() => select(new R.Cons(1, 2), input), /with keys/);
  assert.throws(() => select(R.EMPTY, null), /with map/);
});

test("CompilerData binding references validate byte widths, phase bounds and the closed shape", () => {
  const valid = R.hashMap(R.kw("version"), 1, R.kw("kind"), R.kw("binding-reference"),
    R.kw("world"), "w".repeat(32), R.kw("declaration"), "d".repeat(32), R.kw("id"), "é".repeat(16),
    R.kw("phase"), -4096, R.kw("space"), R.sym("value"));
  const reference = cd("binding_reference?", 1);
  assert.equal(reference(valid), true);
  assert.equal(reference(valid.assoc(R.kw("phase"), 4096)), true);
  for (const [key, value] of [["phase", 4097], ["phase", R.flt(1)], ["id", "é".repeat(32)],
    ["space", R.sym("")], ["space", R.sym("é".repeat(257))], ["version", 2]]) {
    assert.equal(reference(valid.assoc(R.kw(key), value)), false, key);
  }
  assert.equal(reference(valid.assoc(R.kw("extra"), true)), false);
  assert.equal(reference(null), false);
});

test("CompilerData plain-clause shape view is bounded, passive, and distinguishes catch stacks", () => {
  let executed = 0;
  const body = () => { executed++; };
  const pat = R.hashMap(R.kw("pop"), R.kw("pvar"), R.kw("name"), "x");
  const clause = R.hashMap(R.kw("pats"), R.list(pat), R.kw("body"), body);
  const node = (cl) => R.hashMap(R.kw("op"), R.kw("fn"), R.kw("clauses"), R.list(cl));
  const simple = cd("simple_function_clause", 1);
  assert.strictEqual(simple(node(clause)), clause);
  assert.equal(executed, 0);
  assert.equal(simple(node(clause.assoc(R.kw("guard"), true))), null);
  assert.equal(simple(node(clause.dissoc(R.kw("body")))), null);
  assert.equal(simple(node(clause.assoc(R.kw("pats"), new R.Cons(pat, null)))), null);
  assert.notEqual(simple(node(clause.assoc(R.kw("pats"), R.listFromArray(Array(255).fill(pat))))), null);
  assert.equal(simple(node(clause.assoc(R.kw("pats"), R.listFromArray(Array(256).fill(pat))))), null);
  const stacks = cd("catch_stack_bindings", 0)();
  assert.equal(stacks.get(R.kw("frames")), "__STACKTRACE__");
  assert.equal(stacks.get(R.kw("raw")), "__STACKTRACE_RAW__");
});

test("native unit validation and fingerprint serialization refuse explicitly without granting custody", () => {
  for (const key of ["Elixir.BeamLisp.CompilerData/check_contextual_unit!/1", "erlang/term_to_binary/2"]) {
    assert.equal(typeof leaf(key), "function");
    assert.throws(() => leaf(key)(R.EMPTY_MAP, R.list(R.kw("deterministic"))),
      e => e instanceof R.BLError && e.message.includes(key) && /BEAM only/.test(e.message));
  }
  assert.equal(leaf("Elixir.BeamLisp.CompilerData/not_a_function/1"), undefined);
});
