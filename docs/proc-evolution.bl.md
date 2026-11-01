# Versioned owner contracts

`proc.evolve` keeps one native owner PID while replacing its named Source
callbacks and state. Public preparation and commit run under the actual admitted
candidate graph. A prepared spec, namespace name, copied environment or digest
string supplies no execution authority. The spec digest must be the candidate's
actual digest.

Preparation inspects the callbacks' published ANF and retains their native
registration, code, definition and binding identities. Samples add checks; they
do not prove future compatibility. Unsupported proofs refuse before conversion
or publication. Commit rechecks the same identities and owner revision. A stale
revision cannot publish an earlier state observation.

The default upgrade call uses the same 31-second window as explicit preparation
and commit. `:upgrade-ms` separately caps rehearsal; it does not include metadata
analysis. An explicit caller timeout remains authoritative. A timeout after the
receiver has claimed work is an uncertain outcome, not permission to replay
conversion or publish another candidate.

## Messages and replies

The message obligation is `old-accept(m) => new-accept(upcast(m))`, including
operation totality in the supported domain. The reply obligation relates both
arguments: for every accepted old request and every reply satisfying the new
contract at its upcast request, `downcast(reply, original-request)` must satisfy
the old reply contract. Unary callbacks may ignore the request. Each retained
edge preserves its own request and reply checks until its clients drain.

This proves predicate preservation, not handler correctness. A handler can
return an invalid reply or state, or perform an external effect before a runtime
check fails. Runtime checks refuse that result and keep the owner state current;
they cannot undo an already performed handler effect.

The closed fragment includes scalar predicates, fixed native map operations,
small eager vector construction, constant vector projections, bounded cases and
named transitive helpers. Unknown callbacks, lazy forcing, dynamic calls,
foreign constructors, recursive helpers and unchecked protocol dispatch decline.
Universal arithmetic currently requires integer operands; finite floats can
overflow and need separate range evidence.

## An initial bounded data contract

Existing owners default to `:unrestricted`. Their accepted capability and opaque
payload behavior is unchanged. An upgrade cannot change this initial contract by
adding a candidate field.

A managed **standalone SDK owner** can select a bounded first-order contract when
it starts:

```clojure
(generation/with! old-graph
  #(evolve/start! old-spec initial-state
                 {:managed true :message-domain :bounded-first-order}))
```

The runtime authenticates the actual live fixed SDK `proc.evolve/owner`
declaration and native custody during initialization, proof and admission.
Composed Source owners retain their existing contract. Requesting this new scope
on an unsupported owner refuses with `:unsupported-message-domain-owner`; a data
tuple or flag cannot manufacture the native boundary.

From the first request, external messages and handler replies are bounded to
16,384 traversal nodes, 65,536 structural bytes and depth 64. These are the native
first-order validator's costs, not JSON or wire sizes. The domain admits scalar
data, proper lists/maps, exact decimals, symbols and canonical native
vectors/sets. It rejects callbacks, native capabilities, lazy values, foreign
records and malformed collection storage before application callbacks run.
Refusals are `:message-domain-refused` or `:reply-domain-refused`.

Internal conversions have a larger ceiling: 32,768 nodes, 1 MiB and depth 128.
Before publication the prover composes conservative output bounds across all
retained edges. It admits borrowing disjoint input subtrees plus bounded
constructor overhead. Duplication, overlapping subtrees, arbitrary arithmetic
output growth and embedding original requests into reply data decline. Thus an
internal size check cannot silently remove previously admitted old inputs.

The initial first-order premise enables exact vector and plain-map reasoning.
For example, `vector?` alone is insufficient evidence: a raw map can carry a
forged vector tag. Likewise, native map updates cannot treat every raw map as a
plain map; adding/removing fields on a valid vector or set can invalidate its
storage. The prover and runtime both preserve these distinctions.

Owner state has a separate contract. It may contain legitimate opaque native
handles; selecting bounded messages does not reinterpret those handles as data.

## Current-state observation and recovery

State conversion is checked as a read-only observation of the **current** owner
state. Conversion and its candidate invariant run under the existing deadline
and Datom observation guard, followed by runtime value validation. This is not a
universal claim about future database contents or a guarantee that a query will
succeed.

`datom.query.read-only/read!` is the fixed read boundary for this fragment. It
requires an actual live native SDK ETS/Fjall connection and validates the
observed native database view before query-scope dispatch. A matching path,
class spelling or copied receipt grants no connection ownership. Literal query
plans must belong to the existing stored-attribute read fragment. An empty
closed query vocabulary surrounds both validation and execution, so a custom
provider cannot become executable authority between those steps. Results are
bounded eager data. Callback queries, computed providers, rules, pull, raw
database escapes and forged connection fields refuse.

Recovery derives new state from current receipts. It does not rewind storage,
modify database formats, authorize business writes or claim to compensate
unknown external effects. Publication still needs the exact native preparation
and revision CAS; retirement still needs accepted clients and durable work to
drain.
