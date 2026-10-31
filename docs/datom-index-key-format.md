# Datom index key format

New Datom stores use key format 2. Native lists, vectors and finite lazy
sequences with equal elements encode to the same ordered index key, including
when nested inside another value. Metadata does not affect keys. Large integers
and equal floats also share keys; integers between adjacent floats retain their
exact order.

This changes index keys and temporary transaction equality keys. It does not
change `datom.value-codec`: stored native lists remain native lists, vectors
remain vectors, and nested payload representation is preserved.

## Opening existing stores

Datom checks a reserved format descriptor before opening a connection or
constructing a database value. Empty stores are admitted. A new connection
publishes the descriptor before initializing counters or schema. The first
direct `datom.index/write-datoms` call on an empty store commits its descriptor
and index rows together. Query scans do not repeat format admission.

A nonempty store without a descriptor, or with a different descriptor, fails
with `:kind :incompatible-index-key-format` and
`:action :offline-reindex-required`. Admission does not rewrite that store's
schema, counters or data. This refusal is conservative: it also covers a legacy
store whose values happen to be scalar-only.

Do not add the current descriptor to an old store to bypass this check. Legacy
list keys and some large-number keys differ from the current encoding; relabeling
them would leave point lookups, uniqueness and range scans incorrect.

## Upgrade boundary

An offline upgrade must retain the original store and write a separate empty
destination using the current encoder. It must reconstruct all covering indexes
from the stored datom payloads, preserve transaction history and operational
metadata, and rebuild derived indexes. Copying old index keys is not a reindex.
Equal values that previously occupied different keys must be checked for
conflicting uniqueness claims before accepting the destination. Validate the
rebuilt database and preserve a rollback copy before switching applications.

An automated offline reindex command is not included in this change. Persistent
application stores need an explicit upgrade before they can be opened with this
format. Rebuildable Codebase analysis caches select a new cache generation;
their old stores remain untouched.
