# Datom index keys

Index format 2 gives equal sequential and numeric values equal keys. Lists,
vectors, nested collections and metadata-bearing values follow the language's
equality and ordering. Stored payloads retain their original representation.

The SDK owns the reserved descriptor `{:version 2}`. Admission reads it before
schema or counter mutation. A fresh empty store publishes it before connection
initialization; the first direct index commit includes it atomically with data.
Empty-store admission requires the store's bounded `Count` capability.

A nonempty unversioned store requires explicit offline conversion into a separate
generation. Use the deployment's reviewed storage inventory and migration plan;
Foundry retains the original, selects the prepared code/data pair, and grants
writes only after read-only readiness. Recovery preserves admitted data.

Index format, application `dataVersion`, payload encoding and durable
`datom.identity/value-v1` identities are separate contracts. Index upgrades keep
existing credential associated data and migration seals stable. The disposable
Codebase facts cache uses generation `facts-8` and rebuilds automatically.
