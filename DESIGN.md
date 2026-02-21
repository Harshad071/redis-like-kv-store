# RedisLite – System Design (FAANG-Level)

> **Audience:** Senior Backend / Infrastructure Engineers
>
> **Intent:** This document defines the *exact* correctness, durability, and concurrency guarantees of RedisLite. It prioritizes determinism, failure transparency, and reasoning over feature breadth.

---

## 1. Problem Statement

RedisLite is a **single-node, in-memory key–value store** with optional durability. It is explicitly **not** a Redis replacement and makes no claims of horizontal scalability, high availability, or distributed consensus.

The system exists to answer one question:

> *What is the minimum correct design for a durable, concurrent, in-memory KV store?*

---

## 2. Explicit Non-Goals

RedisLite deliberately does **not** support:

* Multi-node replication or clustering
* Consensus protocols (Raft, Paxos)
* Automatic failover or leader election
* Strong real-time guarantees under OS crashes
* High-throughput batching or zero-copy I/O
* Security hardening (auth, TLS, ACLs)

Any design decision conflicting with correctness or clarity is rejected.

---

## 3. Core Abstractions

### 3.1 Data Model

* **Key:** UTF-8 string
* **Value Types:**

  * String (opaque bytes)
  * List (ordered, append-only)
  * Hash (string → string map)

No implicit type coercion is performed. Type violations are runtime errors.

---

## 4. Storage Engine Architecture

### 4.1 In-Memory Store

* Backed by a single `dict`
* All mutations occur under a **global write lock**
* Reads are lock-free only when safe

Rationale: simplicity and invariant preservation over speculative parallelism.

---

### 4.2 Write-Ahead Log (WAL)

* Append-only, line-oriented log
* Each entry represents a **fully-formed mutation**
* WAL is flushed (`fsync`) before memory mutation

**Invariant:**

> If a mutation is visible in memory, it must exist durably in the WAL.

---

### 4.3 Snapshotting

* Periodic full-state serialization
* Snapshot is written to a temporary file and atomically renamed
* WAL is truncated *only after* snapshot success

Snapshots are an optimization, not a correctness requirement.

---

## 5. Concurrency Model

* Single global mutex for writes
* Read operations may proceed concurrently if no mutation is active

### Guarantees:

* Linearizable writes
* Read-your-writes consistency

### Trade-off:

Throughput is intentionally sacrificed to preserve reasoning simplicity.

---

## 6. TTL and Expiration Semantics

* TTLs are stored as absolute timestamps
* Expiration is enforced lazily on access
* Optional background reaper thread

**Guarantee:**

> Expired keys are never returned after their TTL, but may exist internally until accessed.

---

## 7. Crash Consistency Model

RedisLite provides **crash recovery**, not high availability.

### Crash Scenarios Covered:

| Failure Type          | Outcome                   |
| --------------------- | ------------------------- |
| Process crash         | WAL replay restores state |
| Power loss mid-write  | Partial WAL entry ignored |
| Snapshot interruption | Last valid snapshot used  |

### Recovery Algorithm:

1. Load latest valid snapshot
2. Sequentially replay WAL
3. Discard malformed entries

---

## 8. Correctness Invariants

1. WAL precedes memory mutation
2. Memory state == snapshot + WAL replay
3. No partial mutation is ever visible
4. Expired keys are logically invisible

Violating any invariant is considered a **critical bug**.

---

## 9. Failure Modes (Explicit)

RedisLite **does not protect against**:

* Disk corruption
* Concurrent writers bypassing locks
* Clock skew affecting TTL
* Manual WAL edits
* Resource exhaustion (RAM / FD leaks)

These are documented limitations, not oversights.

---

## 10. Testing Strategy

### Mandatory Tests:

* Crash during WAL write
* Crash during snapshot rename
* WAL truncation recovery
* TTL expiration correctness

Correctness tests take priority over performance benchmarks.

---

## 11. Performance Characteristics

* Write latency dominated by `fsync`
* O(1) average-time operations
* Snapshot cost proportional to dataset size

RedisLite optimizes **predictability**, not raw speed.

---

## 12. Design Philosophy

RedisLite follows three principles:

1. **Correctness before throughput**
2. **Explicit guarantees over implicit behavior**
3. **Failure transparency over resilience illusions**

This system is intentionally boring — and therefore trustworthy.

---

## 13. What Would Change in Production

To evolve RedisLite toward production readiness:

* Replace global lock with fine-grained locking
* Introduce background I/O batching
* Add checksums to WAL
* Implement replication protocol
* Add observability (metrics, tracing)

These are *extensions*, not fixes.

---

## 14. Summary

RedisLite is a **correct, inspectable, single-node KV engine**.

It does not attempt to compete with Redis.
It attempts to be *understood*.

That is the design goal.
