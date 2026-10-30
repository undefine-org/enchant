// Exercise the requested compiler/IR modules in the real cold-build output.
// Invoked by test/bl/js_cold_build_test.bl after the application runs.
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const out = path.resolve(process.argv[2]);
const load = name => import(pathToFileURL(path.join(out, name)).href);
await load("ns/base.mjs");
const R = await load("rt.mjs"), { mangle } = await load("host-leaves.mjs");
const anf = await load("ns/anf.mjs"), ir = await load("ns/system.ir.mjs");
const native = await load("ns/system.js.mjs"), pattern = await load("ns/js.pattern.mjs");
const call = (module, name, ...args) => module["d_" + mangle(name)](...args);
const k = R.kw;
const literal = call(anf, "lit", -1);
const remote = call(anf, "remote", k("erlang"), k("abs"), R.list(literal))
  .assoc(k("ann"), R.hashMap(k("file"), "fixture.bl", k("line"), 7, k("private"), true));
assert.deepEqual(call(ir, "child-nodes", remote).h, literal);
assert.equal(call(native, "check", remote).cnt, 0);
assert.equal(typeof pattern["d_" + mangle("lines")], "function");
const dependencies = call(anf, "execution-dependencies", R.list(remote));
assert.equal(dependencies.get(k("nodes")), 2);
assert.equal(dependencies.get(k("complete")), true);
const edge = dependencies.get(k("edges")).h;
assert.equal(edge.get(k("kind")), k("direct-call"));
assert.deepEqual(edge.get(k("target")).items, [k("mfa"), k("erlang"), k("abs"), 1]);
assert.equal(edge.get(k("span")).get(k("line")), 7);
assert.equal(edge.get(k("span")).has(k("private")), false);

// This producer uses all?/each/empty?/group_by and maps/with in compiled ANF,
// with its actual five-field emitted-clause ABI and no native code publication.
const body = k("Elixir.Fixture"), name = k("run");
const clause = R.hashMap(k("op"), k("defn-clause"), k("fname"), name,
  k("params"), R.EMPTY, k("body"), remote, k("guard"), null, k("ann"), R.EMPTY_MAP);
const emitted = R.tup([k("fixed"), 0, name, clause, body]);
const entries = call(anf, "execution-entries", "fixture", "run", R.list(emitted, emitted), R.hashMap(body, "h".repeat(16)));
assert.equal(entries.n, 1);
assert.equal(entries.h.get(k("definition")), "fixture/run");
assert.equal(entries.h.get(k("edges")).n, 2);
assert.equal(entries.h.get(k("dependencies-complete")), true);
assert.throws(() => call(anf, "execution-entries", "fixture", "run", R.EMPTY, R.EMPTY_MAP));

const { LEAVES } = await load("leaves.mjs");
for (const key of ["Elixir.BeamLisp.CompilerData/check_contextual_unit!/1", "erlang/term_to_binary/2"]) {
  assert.throws(() => LEAVES[key](R.EMPTY_MAP, R.list(k("deterministic"))), /BEAM only/);
}
assert.throws(() => call(anf, "execution-clause-identities", R.list(clause)), /term_to_binary\/2.*BEAM only/);
assert.throws(() => call(anf, "contextual-unit-body", R.EMPTY_MAP, literal), /check_contextual_unit!\/1.*BEAM only/);
console.log("JS_IR_BUNDLE_OK");
