# RedisLite

## A Crash-Safe, Single-Node In-Memory Key–Value Store (Systems Engineering Project)

> **Positioning statement (read this first):**
> RedisLite is **not Redis**, not a Redis clone, and not production-ready.
> This project exists to demonstrate **deep understanding of storage-system fundamentals**, specifically **durable persistence and crash recovery** in a single-node key–value store.

Everything in this repository is intentionally scoped. Features that dilute correctness are omitted on purpose.

---

## Why This Project Exists

Modern databases are hard not because of APIs, but because of **failure modes**:

* Power loss
* Partial writes
* Process crashes
* Corrupted logs

RedisLite was built to answer one question rigorously:

> *How do you make a simple in-memory key–value store survive crashes without losing correctness?*

This repository is the answer.

---

## Explicit Non-Goals

RedisLite intentionally does **not** implement:

* Networking or client/server protocol
* Clustering or replication
* Pub/Sub
* Lua scripting
* Advanced Redis data types
* High-throughput optimizations

If you are looking for those, use Redis.

---

## System Overview

RedisLite is a **single-process, single-node** key–value store with:

* In-memory state
* Write-Ahead Logging (WAL)
* Snapshot-based persistence
* Deterministic crash recovery

The system prioritizes **correctness, durability, and transparency** over performance.

---

## Architecture

### Core Components

```
+-------------------+
|  Client (CLI/API) |
+-------------------+
          |
          v
+-------------------+
| In-Memory KV Map  |  ← authoritative runtime state
+-------------------+
          |
          v
+-------------------+
| Write-Ahead Log   |  ← durability before mutation
+-------------------+
          |
          v
+-------------------+
| Snapshot Engine   |  ← periodic full-state persistence
+-------------------+
```

---

## Persistence Model (Core Focus)

### Write-Ahead Log (WAL)

* Every mutating operation is **appended to disk before being applied in memory**
* Log entries are:

  * Sequential
  * Checksummed
  * Idempotent on replay

**Guarantee:**

> If an operation is acknowledged, it will survive a crash.

---

### Snapshotting

* Periodic full-state snapshots
* Written to a temporary file
* Atomically promoted via rename

**Guarantee:**

> Snapshots are either fully valid or ignored.

---

### Crash Recovery

On startup:

1. Load latest valid snapshot
2. Replay WAL entries newer than the snapshot
3. Skip corrupted or partial log entries safely

Crash recovery is **deterministic** and **repeatable**.

---

## Failure Modes (Explicitly Documented)

| Failure Scenario           | Outcome                            |
| -------------------------- | ---------------------------------- |
| Process crash during write | WAL replay restores state          |
| Power loss mid-log-write   | Partial entry detected and ignored |
| Crash during snapshot      | Snapshot discarded safely          |
| Disk full                  | Writes fail explicitly             |

This system **fails loudly**, not silently.

---

## Concurrency Model

* Single writer model
* Coarse-grained locking around mutations

**Rationale:**
Concurrency complexity is intentionally minimized to keep durability reasoning correct and auditable.

---

## TTL Support (Secondary Feature)

* Keys may have optional expiration timestamps
* TTL is enforced lazily during access
* Expired keys are removed before read or write

TTL is implemented for realism but is **not the focus of this project**.

---

## CLI Example

```
> SET user Harshad
OK
> GET user
Harshad
> DEL user
1
```

This CLI directly interacts with the in-process store. There is no network protocol.

---

## Python API Example

```python
from redislite import RedisLite

store = RedisLite()
store.set("name", "Harshad")
print(store.get("name"))
```

---

## Testing Strategy

### What Is Tested

* WAL append correctness
* Crash recovery determinism
* Snapshot atomicity
* Idempotent log replay
* TTL expiration behavior

### How Crashes Are Tested

* Forced process termination
* Partial log writes
* Interrupted snapshot creation

### What Is NOT Tested

* Distributed failures
* Network partitions
* High-concurrency scaling

---

## Performance Notes

RedisLite is **not optimized for throughput**.

Expected characteristics:

* Higher latency than Redis
* Predictable correctness under failure
* Linear log replay time

Performance trade-offs are documented, not hidden.

---

## Project Structure

```
RedisLite/
├── redislite.py        # Core KV store
├── wal.py              # Write-ahead logging
├── snapshot.py         # Snapshot persistence
├── recovery.py         # Crash recovery logic
├── cli.py              # Interactive CLI
├── tests/              # Crash + persistence tests
├── DESIGN.md           # System invariants & reasoning
└── README.md
```

---

## What This Project Demonstrates

* Understanding of durability guarantees
* Correct use of WAL
* Crash recovery reasoning
* Atomic file operations
* Engineering restraint and scope control

---

## Who This Project Is For

* Backend engineers
* Systems programming learners
* Reviewers evaluating engineering depth

This repository is meant to be **read**, not just run.

---

## License

MIT License © 2026 Harshad Jadhav

---

## Final Note to Reviewers

This project intentionally chooses **depth over breadth**.

If you are evaluating RedisLite, judge it on:

* Correctness
* Failure handling
* Design clarity

Not on feature count.
