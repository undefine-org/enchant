import {test} from "node:test";
import assert from "node:assert/strict";
import * as R from "../../priv/lib/js/rt.mjs";
import * as Z from "../../priv/lib/js/lazy.mjs";
import {LEAVES as L} from "../../priv/lib/js/leaves.mjs";

const kw = R.kw, T = (...xs) => new R.Tup(xs), list = R.list,
  check = L["Elixir.BeamLisp.CompilerData/check_first_order!/2"],
  reader = L["Elixir.BeamLisp.CompilerData/check_reader_data!/1"],
  requireSpec = L["Elixir.BeamLisp.CompilerData/namespace_require_spec/1"],
  clauses = L["Elixir.BeamLisp.CompilerData/namespace_clauses/1"],
  excludes = L["Elixir.BeamLisp.CompilerData/namespace_core_excludes/1"],
  opts = (name, value) => R.hashMap(kw(name), value),
  array = (xs) => { const out = []; for (let p = xs; p !== R.EMPTY; p = p.t) { assert.ok(p instanceof R.Cons); out.push(p.h); } return out; },
  symbol = (name) => T(kw("symbol"), name), keyword = (name) => T(kw("keyword"), name),
  vector = (...xs) => T(kw("vector"), list(...xs)), form = (...xs) => T(kw("list"), list(...xs));

// The BL wrapper supplies outcomes measured against the installed native
// validator for these same values/options, including exact budget boundaries.
const fixtures = [
  ["scalar", 1, R.EMPTY_MAP], ["small-int-bytes", 1, opts("max-bytes", 3)],
  ["integer-bytes", 256, opts("max-bytes", 5)], ["negative-bytes", -1, opts("max-bytes", 5)],
  ["bignum-bytes", 18446744073709551616n, opts("max-bytes", 12)],
  ["float-bytes", R.flt(1.5), opts("max-bytes", 9)],
  ["unicode-bytes", "é", opts("max-bytes", 1)], ["nil-bytes", null, opts("max-bytes", 2)],
  ["list-nodes", list(1, 2), opts("max-nodes", 2)],
  ["vector-nodes", R.vecFromArray([1, 2]), opts("max-nodes", 3)],
  ["map-nodes", R.hashMap(kw("x"), 1), opts("max-nodes", 2)],
  ["set-nodes", R.hashSet(1), opts("max-nodes", 3)],
  ["nested-depth", list(list(list(1))), opts("max-depth", 2)],
  ["invalid-limits", 1, opts("max-nodes", 0)],
  ["native-tuple", T(kw("x"), 1), R.EMPTY_MAP],
  ["improper-list", new R.Cons(1, kw("tail")), R.EMPTY_MAP],
  ["opaque-function", () => 1, R.EMPTY_MAP],
  ["foreign-struct", R.hashMap(kw("__struct__"), kw("foreign")), R.EMPTY_MAP],
  ["symbol-metadata", T(kw("meta"), symbol("x"), R.hashMap(kw("owner"), "test")), R.EMPTY_MAP],
  ["metadata-nodes", T(kw("meta"), symbol("x"), R.hashMap(kw("owner"), "test")), opts("max-nodes", 2)],
];
function outcome(value, options) {
  try { assert.equal(check(value, options), value); return "accepted"; }
  catch (error) {
    if (!(error.data instanceof R.HMap)) throw error;
    return error.data.get(kw("kind")).fq + ":" + error.data.get(kw("reason")).fq;
  }
}
test("first-order admission matches native outcomes and exact budget boundaries", () => {
  const actual = fixtures.map(([name, value, options]) => [name, outcome(value, options)]);
  const expected = process.argv[2] ? JSON.parse(process.argv[2]) : fixtures.map(([name]) => [name,
    ["scalar", "small-int-bytes", "symbol-metadata"].includes(name) ? "accepted" :
      "unsafe-first-order-data:" + ({"integer-bytes":"byte-limit", "negative-bytes":"byte-limit", "bignum-bytes":"byte-limit", "float-bytes":"byte-limit", "unicode-bytes":"byte-limit", "nil-bytes":"byte-limit", "list-nodes":"node-limit", "vector-nodes":"node-limit", "map-nodes":"node-limit", "set-nodes":"node-limit", "nested-depth":"depth-limit", "invalid-limits":"invalid-limits", "native-tuple":"native-tuple", "improper-list":"improper-list", "opaque-function":"opaque-value", "foreign-struct":"foreign-struct", "metadata-nodes":"node-limit"})[name]]);
  assert.deepEqual(actual, expected);
});

test("dense/trie vectors, decimals and reserved set members remain data", () => {
  for (const value of [R.vecFromArray([]), R.vecFromArray([1, 2]), R.vecFromArray(Array.from({length:1100}, (_, i) => i)),
    R.dec(123n, 2), R.hashSet(kw("__struct__")), R.hashMap(kw("a"), list(1, symbol("x")))]) assert.equal(check(value, R.EMPTY_MAP), value);
});

test("raw guards refuse resources, callbacks and malformed storage without forcing", () => {
  let calls = 0;
  const lazy = Z.newLazy(() => { calls++; return list(1); });
  const accessor = new R.Cons(1, R.EMPTY);
  Object.defineProperty(accessor, "h", {get() { calls++; return 1; }});
  const map = R.hashMap(kw("a"), 1);
  map.entries = () => { calls++; throw new Error("public enumeration"); };
  assert.equal(check(map, R.EMPTY_MAP), map);
  const vectorValue = R.vecFromArray(Array.from({length:33}, (_, i) => i));
  vectorValue.toList = () => { calls++; throw new Error("public vector traversal"); };
  assert.equal(check(vectorValue, R.EMPTY_MAP), vectorValue);
  for (const value of [lazy, new R.Atom(1), R.makeRef(), {}, accessor,
    new R.Vec(33, 5, [], [1], null), new R.HSet(R.hashMap(kw("x"), null)),
    new R.Vec(1, 5, [], [1], R.hashMap(kw("hidden"), () => calls++))]) {
    assert.throws(() => check(value, R.EMPTY_MAP), /bounded first-order/);
  }
  assert.throws(() => reader(lazy), /invalid_reader_data/);
  assert.throws(() => reader(new R.Cons(1, lazy)), /invalid_reader_data/);
  const cycle = new R.Cons(1, R.EMPTY); cycle.t = cycle;
  assert.throws(() => check(cycle, opts("max-nodes", 10)), /bounded first-order/);
  const badMap = R.hashMap(kw("x"), 1); badMap.root = {arr:[]};
  assert.throws(() => check(badMap, R.EMPTY_MAP), /bounded first-order/);
  assert.equal(calls, 0);
});

test("Reader and namespace grammar preserve nodes and enforce the native grammar", () => {
  const marked = T(kw("meta"), symbol("dep"), R.hashMap(kw("line"), 1));
  assert.equal(reader(marked), marked);
  assert.deepEqual(requireSpec(marked).items, ["dep", null, R.EMPTY]);
  const required = requireSpec(vector(symbol("dep"), keyword("as"), symbol("d"), keyword("refer"), vector(symbol("f"), symbol("g"))));
  assert.deepEqual(required.items.slice(0, 2), ["dep", "d"]);
  assert.deepEqual(array(required.items[2]), ["f", "g"]);
  assert.equal(requireSpec(vector(symbol("dep"), keyword("refer"), keyword("all"))).items[2], kw("all"));
  for (const invalid of [vector(), vector(keyword("dep")), vector(symbol("dep"), keyword("as")),
    vector(symbol("dep"), keyword("as"), symbol("a"), keyword("as"), symbol("b")),
    vector(symbol("dep"), keyword("refer"), vector(symbol("f"), symbol("f"))),
    vector(symbol("dep"), keyword("rename"), R.EMPTY_MAP)]) assert.throws(() => requireSpec(invalid), /invalid_namespace_require/);
  const original = list(form(keyword("require"), symbol("dep")), form(keyword("refer-clojure"), keyword("exclude"), vector(symbol("map"))));
  assert.equal(clauses(original), original);
  assert.equal(clauses(new R.Cons("docs", original)), original);
  assert.deepEqual(array(excludes(list(keyword("exclude"), vector(symbol("map"), symbol("filter"))))), ["map", "filter"]);
  assert.throws(() => clauses(list(symbol("invalid"))), /invalid_namespace_header/);
  assert.throws(() => excludes(list(keyword("exclude"))), /invalid_namespace_excludes/);
  assert.throws(() => reader(R.vecFromArray([1])), /invalid_reader_data/);
  assert.throws(() => reader(R.hashMap(kw("__struct__"), kw("foreign"))), /invalid_reader_data/);
});

test("compiler collection leaves retain native callback order and result shapes", () => {
  const calls = [], xs = list(3, 1, 2);
  assert.deepEqual(array(L["Elixir.Enum/filter/2"](xs, x => { calls.push(x); return x !== 1; })), [3, 2]);
  assert.deepEqual(calls.splice(0), [3, 1, 2]);
  const result = L["Elixir.Enum/map_reduce/3"](xs, 0, (x, acc) => { calls.push(x); return T(x * 2, acc + x); });
  assert.deepEqual(array(result.items[0]), [6, 2, 4]); assert.equal(result.items[1], 6);
  assert.deepEqual(calls.splice(0), [3, 1, 2]);
  assert.deepEqual(array(L["Elixir.Enum/reverse/1"](xs)), [2, 1, 3]);
  assert.deepEqual(array(L["Elixir.Enum/with_index/1"](xs)).map(pair => pair.items), [[3,0],[1,1],[2,2]]);
  assert.deepEqual(array(L["Elixir.Enum/sort_by/2"](list("a", 1, kw("a")), x => { calls.push(x); return x; })), [1,kw("a"),"a"]);
  assert.deepEqual(calls, ["a", 1, kw("a")]);
  assert.equal(L["Elixir.Map/new/1"](list(T(kw("a"), 1), T(kw("a"), 2))).get(kw("a")), 2);
  assert.throws(() => L["Elixir.Map/new/1"](list(R.vecFromArray([kw("a"), 1]))), /Map.new entry/);
  assert.throws(() => L["Elixir.Enum/filter/2"](null, () => true), /Enumerable/);
  assert.equal(L["Elixir.Atom/to_string/1"](null), "nil");
  const key = kw("compiler-boundary-test");
  assert.equal(L["erlang/erase/1"](key), kw("undefined"));
  L["erlang/put/2"](key, 9);
  assert.equal(L["erlang/erase/1"](key), 9);
  assert.equal(L["erlang/get/1"](key), kw("undefined"));
});

test("native SDK constructor and class metadata never acquire JavaScript authority", () => {
  for (const [module, name, arity] of [["AOT","sdk_constructor_binding_reference",2], ["AOT","sdk_constructor_declaration_kind",2],
    ["AOT","constructor_call!",5], ["Record","declaration_descriptor",5]]) {
    assert.equal(L["erlang/function_exported/3"](kw("Elixir.BeamLisp." + module), kw(name), arity), false);
    assert.throws(() => L["Elixir.BeamLisp." + module + "/" + name + "/" + arity](...Array(arity).fill(null)), /BEAM only/);
  }
});
