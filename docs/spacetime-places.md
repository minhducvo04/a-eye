# Memory locations and the SpacetimeDB handoff

`STORE=local` is the default. `STORE=spacetime` selects the official HTTP API adapter in
`server/memory_storage.py`; existing memory callers use the same `Store` methods. The teammate must install
the module definitions below before enabling that switch. This package does not publish a database.

## Configuration and ownership

Use the existing Makefile to load `.env`; never put credentials in command arguments or logs. Required names:

```text
STORE
SPACETIMEDB_URI
SPACETIMEDB_MODULE
SPACETIMEDB_TOKEN
A_EYE_MEMORY_KEY
```

`SPACETIMEDB_URI` is the origin, e.g. `https://maincloud.spacetimedb.com`, with no database path.
HTTPS is mandatory except for loopback development. `SPACETIMEDB_MODULE` is the database name or identity.
`SPACETIMEDB_TOKEN` is a caller token, preferably not the database administrator's token.
`A_EYE_MEMORY_KEY` is the existing Fernet master key; remote storage refuses missing or malformed keys.
Local storage preserves its existing optional encryption behavior and status reporting.

**One configured token supports one application owner.** The module's owner is always `ctx.sender`, never a
reducer argument. The adapter claims that caller with an HMAC of the authenticated application owner, rejects
a different owner using the same token, and derives that user's encryption key with HKDF-SHA256. The existing
HTTP and WebSocket authentication supplies the application owner; a client cannot choose it in a memory request.
Two independent users need separate SpacetimeDB caller tokens/server instances for this demo. A shared service
token plus a client-supplied owner string is not a supported multi-user deployment.

Private mode and `LOCAL_ONLY=1` select local storage for newly opened stores. An already-open remote store
checks the privacy gate before **every** request, including reads and deletes. It fails closed without switching
data stores mid-operation. Remote errors are generic; response bodies, credentials and private rows are not
logged. There are no redirects, automatic retries, or silent fallbacks after remote failure.

## Logical graph and queries

| Row | Fields after local decryption |
| --- | --- |
| `things` | `id`, `owner`, `name`, `kind`, `created` (Unix seconds) |
| `placements` | `id`, `thing_id`, `owner`, `place_path` (outermost first), `t` (Unix seconds), `source` (`tag`, `capture`, `vision`), `confidence` (0–1) |

Names identify one thing per owner, case-insensitively. Distinguish two similar objects with explicit names.
Current location is the maximum `(t, id)` placement; random IDs provide a deterministic tie-break for equal
timestamps, not inferred ordering. Late-arriving older observations do not replace the current location.
History is retained until the existing retention window or explicit Forget removes it. `last_move` returns the
newest transition between different paths, not a repeated sighting or the initial observation. A prefix compares
complete path components, case-insensitively: `desk` matches `desk / drawer`, but not `desktop`.

```python
store.place('keys', ['desk', 'drawer', 'blue bin'], source='tag', confidence=1)
store.where('keys')                 # newest placement, or None
store.in_place(['desk', 'drawer'])   # current contents only, including nested places
store.last_move('keys')             # Unix seconds, or None if no move was observed
store.placements(thing_id)          # complete retained history, ordered by (t, id)
```

`tag_item` and `POST /api/memory/tag` accept optional `place_path`. A tag without it creates a thing, but does
not claim a current location. `home` remains the preferred home, not an observation. `find_item` and
`POST /api/memory/find` read the selected graph, then retain existing text/label search for older records.
Vision sightings with a confident object and nearby landmark contribute a relational one-component path,
such as `["by the left desk"]`; this does not infer containment or a room hierarchy. Capture records remain
text-only unless an upstream producer supplies a structured placement; caption prose is not parsed into facts.

Recent memory stays in RAM when persistent memory consent is off. With both existing consents and remembering
enabled, its text-only entries use the selected store too. Reads retain the two-minute and current-call gates;
call teardown attempts to clear the persisted recent entries. Privacy or network failures are logged without
personal data and do not interrupt teardown; the remote entries remain until a later successful expiry/Forget
write. Crash leftovers are discarded lazily on subsequent writes.
Long-term recall uses the same store and keeps its before-call/yesterday time bounds. Forget also clears the
graph and recent entries as appropriate. Turning memory off does not itself mean Forget.

## Encryption and migration boundary

HKDF uses the decoded 32-byte Fernet master, salt `a-eye-places-v1`, and the authenticated application owner
as `info`. The owner binding is HMAC-SHA256 over `a-eye-owner-v1\0` plus that owner. Each personal field is
Fernet-encrypted JSON `[owner_binding, row_id, field_name, value]`. On read, all three binding fields must match;
swapped or corrupted ciphertext fails closed. Remote thing `name`, `kind`, `created` and placement `place_path`,
`t`, `source`, `confidence` are ciphertext strings. Record/document bodies are encrypted allowlisted metadata.
Frames, audio, crops, embeddings and arbitrary source payloads are never uploaded by this adapter.

Opaque row IDs, row links, caller identity, document names, ciphertext lengths, Fernet creation timestamps and
request timing remain visible to the service. Prefix queries and ordering happen after local decryption; this
is intentionally a small graph, not a scalable encrypted search index. The server can decrypt today: this is
**not end-to-end encryption**. Keep the master stable and backed up; there is no automatic key rotation or
recovery. The next step is a client-generated per-user key, authenticated per-user SpacetimeDB tokens, client
encryption/decryption, and a versioned key-wrapping/migration path. The server would then relay ciphertext and
could no longer perform these plaintext queries itself.

Switching stores does not migrate or erase old local data. The offline seven-table export in
`docs/data-export.md` and `schemas/export-v1.json` remains unchanged. This operational graph is a separate
schema; do not reinterpret v1 `memory_event` rows or automatically export personal memory.

## Exact module definitions (TypeScript)

The following is a complete module entry point using the official `spacetimedb/server` API. Integrate its
tables, reducers and views into the teammate's module; preserve these exported names and argument order.
All base tables are private. The only public read surfaces are caller-filtered views. Reducers take typed
arguments, never arbitrary SQL or a JSON command dispatcher. Ciphertext is a string because the module does
not hold the decryption key; logical path/time/confidence validation happens before encryption in our server.

```typescript
import { schema, table, t, SenderError } from 'spacetimedb/server';

const owners = table({ public: false }, {
  owner: t.identity().primaryKey(), subject: t.string(),
});
const things = table({ public: false }, {
  id: t.string().primaryKey(), owner: t.identity().index('btree'),
  name: t.string(), kind: t.string(), created: t.string(),
});
const placements = table({ public: false }, {
  id: t.string().primaryKey(), owner: t.identity().index('btree'),
  thing_id: t.string().index('btree'), place_path: t.string(),
  t: t.string(), source: t.string(), confidence: t.string(),
});
const documents = table({ public: false }, {
  key: t.string().primaryKey(), owner: t.identity().index('btree'),
  id: t.string(), body: t.string(),
});
const records = table({ public: false }, {
  key: t.string().primaryKey(), owner: t.identity().index('btree'),
  id: t.string(), body: t.string(),
});
const db = schema({ owners, things, placements, documents, records });
export default db;

function opaqueId(id: string) {
  if (!/^[a-f0-9]{32,64}$/.test(id)) throw new SenderError('invalid id');
}
function sealed(value: string, max = 8192) {
  if (value.length < 80 || value.length > max || !/^[A-Za-z0-9_-]+=*$/.test(value))
    throw new SenderError('invalid encrypted field');
}

export const claim_memory = db.reducer({ subject: t.string() }, (ctx, { subject }) => {
  if (!/^[a-f0-9]{64}$/.test(subject)) throw new SenderError('invalid subject');
  const old = ctx.db.owners.owner.find(ctx.sender);
  if (old && old.subject !== subject) throw new SenderError('owner already bound');
  if (!old) ctx.db.owners.insert({ owner: ctx.sender, subject });
});

const thingArgs = { id: t.string(), name: t.string(), kind: t.string(), created: t.string() };
export const put_thing = db.reducer(thingArgs, (ctx, args) => {
  opaqueId(args.id);
  sealed(args.name); sealed(args.kind); sealed(args.created);
  const old = ctx.db.things.id.find(args.id);
  if (old && !old.owner.isEqual(ctx.sender)) throw new SenderError('not owner');
  if (old) ctx.db.things.id.update({ ...old, name: args.name, kind: args.kind });
  else ctx.db.things.insert({ ...args, owner: ctx.sender });
});

export const place_thing = db.reducer({
  ...thingArgs, placement_id: t.string(), place_path: t.string(),
  at: t.string(), source: t.string(), confidence: t.string(),
}, (ctx, args) => {
  // These are direct calls inside the same transaction, not another network reducer invocation.
  put_thing(ctx, { id: args.id, name: args.name, kind: args.kind, created: args.created });
  opaqueId(args.placement_id);
  sealed(args.place_path); sealed(args.at); sealed(args.source); sealed(args.confidence);
  if (ctx.db.placements.id.find(args.placement_id)) throw new SenderError('placement already exists');
  ctx.db.placements.insert({ id: args.placement_id, owner: ctx.sender, thing_id: args.id,
    place_path: args.place_path, t: args.at, source: args.source, confidence: args.confidence });
});

export const put_document = db.reducer({ id: t.string(), body: t.string() }, (ctx, { id, body }) => {
  if (!['tags.json', 'settings.json', 'videos.json', 'recent.json'].includes(id))
    throw new SenderError('unknown document');
  sealed(body, 8 * 1024 * 1024);
  const key = ctx.sender.toHexString() + ':' + id;
  const row = { key, owner: ctx.sender, id, body };
  if (ctx.db.documents.key.find(key)) ctx.db.documents.key.update(row);
  else ctx.db.documents.insert(row);
});

export const put_record = db.reducer({ id: t.string(), body: t.string() }, (ctx, { id, body }) => {
  opaqueId(id); sealed(body, 128 * 1024);
  const key = ctx.sender.toHexString() + ':' + id;
  const row = { key, owner: ctx.sender, id, body };
  if (ctx.db.records.key.find(key)) ctx.db.records.key.update(row);
  else ctx.db.records.insert(row);
});

export const delete_memory_rows = db.reducer({
  thing_ids: t.array(t.string()), placement_ids: t.array(t.string()),
  record_ids: t.array(t.string()), document_ids: t.array(t.string()),
}, (ctx, args) => {
  for (const id of args.thing_ids) {
    const row = ctx.db.things.id.find(id);
    if (row && !row.owner.isEqual(ctx.sender)) throw new SenderError('not owner');
    if (!row) continue;
    for (const p of [...ctx.db.placements.thing_id.filter(id)]) {
      if (!p.owner.isEqual(ctx.sender)) throw new SenderError('not owner');
      ctx.db.placements.id.delete(p.id);
    }
    ctx.db.things.id.delete(id);
  }
  for (const id of args.placement_ids) {
    const row = ctx.db.placements.id.find(id);
    if (row && !row.owner.isEqual(ctx.sender)) throw new SenderError('not owner');
    if (row) ctx.db.placements.id.delete(id);
  }
  for (const id of args.record_ids) ctx.db.records.key.delete(ctx.sender.toHexString() + ':' + id);
  for (const id of args.document_ids) ctx.db.documents.key.delete(ctx.sender.toHexString() + ':' + id);
});

export const my_owners = db.view({ name: 'my_owners', public: true }, t.array(owners.rowType), ctx => {
  const row = ctx.db.owners.owner.find(ctx.sender);
  return row ? [row] : [];
});
export const my_things = db.view({ name: 'my_things', public: true }, t.array(things.rowType),
  ctx => [...ctx.db.things.owner.filter(ctx.sender)]);
export const my_placements = db.view({ name: 'my_placements', public: true }, t.array(placements.rowType),
  ctx => [...ctx.db.placements.owner.filter(ctx.sender)]);
export const my_documents = db.view({ name: 'my_documents', public: true }, t.array(documents.rowType),
  ctx => [...ctx.db.documents.owner.filter(ctx.sender)]);
export const my_records = db.view({ name: 'my_records', public: true }, t.array(records.rowType),
  ctx => [...ctx.db.records.owner.filter(ctx.sender)]);
```

Reducers derive ownership independently of the optional application-owner binding. This permits the synthetic
probe to use the caller's own namespace without permanently claiming a production token. Database owners and
administrators retain their platform privileges; the private tables and filtered views govern ordinary callers.
Ciphertext protects personal content from the database operator, but not from this application's key-holding server.

## Wire calls and examples

Writes use `POST /v1/database/{module}/call/{reducer}` with a JSON **array** of typed arguments in declaration
order and `Authorization: Bearer …`. Reads use `POST /v1/database/{module}/sql`, `Content-Type: text/plain`,
and fixed SELECTs against `my_*` views. There is no caller-built SQL or SQL mutation endpoint in the adapter.
The SQL response is `[ { "schema": …, "rows": [[column1, column2, …]] } ]`.
See the official [HTTP API](https://spacetimedb.com/docs/http/database/),
[reducers](https://spacetimedb.com/docs/functions/reducers/),
[views](https://spacetimedb.com/docs/functions/views/) and
[table permissions](https://spacetimedb.com/docs/tables/access-permissions/) references.

Synthetic **decrypted** rows (illustrative IDs, not import payloads):

```json
{"id":"11111111111111111111111111111111","owner":"synthetic-owner","name":"keys","kind":"object","created":1792843200}
{"id":"22222222222222222222222222222222","thing_id":"11111111111111111111111111111111","owner":"synthetic-owner","place_path":["desk","drawer","blue bin"],"t":1792843201,"source":"tag","confidence":1.0}
{"id":"33333333333333333333333333333333","thing_id":"11111111111111111111111111111111","owner":"synthetic-owner","place_path":["entryway","bowl"],"t":1792843260,"source":"vision","confidence":0.8}
```

The stored thing is `{id: "111…", owner: ctx.sender, name: "<Fernet>", kind: "<Fernet>",
created: "<Fernet>"}`. Each placement preserves opaque IDs and caller identity, while its path, time, source and
confidence are separate ciphertexts. These placeholders are explanatory, not valid ciphertext examples.

## Verification and remaining integration

```sh
make places-live-check PY=/path/to/project/.venv/bin/python
make test PY=/path/to/project/.venv/bin/python
```

The live command checks presence through Make (so `.env` loads), writes one encrypted synthetic thing and
placement, reads only those IDs, deletes them in `finally`, then verifies both are absent. It uses an ephemeral
synthetic key, never reads personal records, never alters the owner binding and never publishes a module.
If any connection variable is missing it prints SKIP. If a request or cleanup fails it prints FAIL; do not treat
that as cleanup proof. A timeout may have committed, so a failed cleanup needs the teammate's reconciliation.
Tests use a fake SpacetimeDB HTTP transport and synthetic local storage. See
[`docs/results/places-db.md`](results/places-db.md) for actual commands and results.
The exact module block above passed strict TypeScript 5.9.3 checking against the official SpacetimeDB 2.13.0
SDK. This checks API/type compatibility; it is not deployed-module or live authorization proof.

This demo uses synchronous bounded HTTP calls and whole-owner metadata reads. Writes of a note, graph and
settings are separate operations; `place_thing` itself is atomic. Concurrent edits of the same tags/recent
document can overwrite each other, and simultaneous first sightings of one name can create duplicate things.
Use one active writer per owner until the teammate adds revision checks or per-entry reducers. Remote requests
are subject to the existing cloud-budget gate and HTTPX usage-meter boundary when a call meter is active.
