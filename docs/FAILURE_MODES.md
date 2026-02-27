# Failure Modes Documentation (Elite Feature #8)

Real production systems document what happens when things go wrong.

## 1. Disk Full

### Symptoms
- Writes start failing with "No space left on device"
- Server continues to run
- New clients connect normally
- Reads still work

### Behavior During Disk Full
```
Client sends: SET key value
RedisLite processes normally
At fsync step: OSError: [Errno 28] No space left on device
Response: -ERR No space on disk

Server state: Healthy, waiting for space
Data state: In-memory (not persisted)
Action: None (waits for admin intervention)
```

### Recovery
```
1. Identify large files (AOF log, snapshots)
2. Rotate/delete old snapshots: rm data/dump.*.bak
3. Truncate AOF if corrupted: echo "" > data/aof.wal
4. Restart server
5. Replication catches up (if enabled)
```

### Prevention
```bash
# Monitor disk space
df -h /data

# Set up alerting
if [[ $(df /data | awk 'NR==2 {print $5}' | cut -d% -f1) -gt 80 ]]; then
    alert_disk_full
fi

# Implement rotation
logrotate -d /etc/logrotate.d/redislite
```

### Mitigation
- Snapshot every 60s (not 30s) to reduce churn
- Compress AOF when rotated
- Set max_memory_mb to prevent OOM swaps

---

## 2. Out of Memory (OOM)

### Symptoms
- Process killed by OS
- Or, LRU eviction starts rapidly
- GET/SET latency spikes (eviction overhead)
- Client receives -ERR OOM eviction failed

### Behavior During OOM
```
max_memory_mb = 100
Current: 102MB

SET key value
→ Eviction triggered
→ Remove oldest key from LRU
→ Repeat until memory < 100MB

Repeat:
  Process writes
  Eviction every 200-300 writes
  Latency: 10µs → 100µs (10x spike)
```

### Recovery
```
1. Immediate: Configure lower max_memory_mb
2. Restart: REDISLITE_MAX_MEMORY_MB=50 (halve it)
3. Monitor: Track eviction_rate
4. If eviction_rate > 100/sec: OOM is looming
5. Manual purge: FLUSHDB or selective DELs
```

### Prevention
```bash
# Monitor memory usage
redis-cli INFO memory

# Set up alerting
if memory_used > max_memory * 0.9:
    alert_memory_high
    trigger_emergency_flushdb  # Cache-specific

# Implement cache expiration
SET key value EX 3600  # Always set TTL for cache
```

### Mitigation
- Use TTL on all cache entries
- Implement rate limiting on SET
- Distribute cache load across multiple instances
- Use Redis's memory-efficient encoding

---

## 3. Replica Disconnected / Network Partition

### Symptoms
- Replica stops syncing
- Replication lag increases indefinitely
- Master continues normally
- Reads from replica return stale data

### Behavior During Disconnect
```
Master (port 6380): Running normally
Replica (port 6381): Connected, replicating

[Network partition: TCP timeout ~60s]

Master: Tries to send commands to replica
        → Socket times out
        → Closes connection
        → Marks replica as disconnected

Replica: Tries to read from master
         → Timeout (60s)
         → Reconnects, full SYNC needed

Data during partition:
- Master: Always fresh
- Replica: Stale (1-60s behind)
- Writes: ONLY on master (not replicated to replica)
```

### Recovery
```
Automatic:
1. Replica detects master disconnected
2. Attempt reconnect (exponential backoff)
3. On success: PSYNC (partial sync if available)
4. On failure: FULLSYNC (full resync)

Manual:
1. Restart replica: REDISLITE_REPLICA_ENABLED=true REDISLITE_REPLICA_HOST=master
2. Check status: redis-cli INFO replication
3. Force resync: redis-cli DEBUG REPLCONF force_resync
```

### Monitoring
```python
# Check replication status
redis-cli INFO replication

# Output:
role:master
connected_replicas:2
replica0:ip=10.0.0.5,port=6379,state=online,lag=0
replica1:ip=10.0.0.6,port=6379,state=online,lag=4500
```

### Mitigation
- Use PSYNC (partial resync) to avoid full sync
- Monitor replication_lag continuously
- Alert if lag > 10 seconds
- Use multiple replicas for redundancy
- Implement connection pooling with retries

---

## 4. Corrupted WAL (Write-Ahead Log)

### Symptoms
- Startup takes longer than expected
- "CRC mismatch at offset X" in logs
- Some recent writes missing
- Server recovers but loses last transactions

### Behavior During WAL Corruption
```
Corrupt WAL file: aof.wal
[length=100][json][CRC32]  ← valid
[length=50][json][CRC32]   ← valid
[length=200][bad JSON][bad CRC32]  ← CORRUPTED!
[length=100][json][CRC32]  ← never reached

Startup recovery:
1. Load snapshot (95% of data)
2. Start replaying WAL
3. Record #1: Valid, apply
4. Record #2: Valid, apply
5. Record #3: CRC MISMATCH!
   → Stop replaying here
   → Log warning: "Skipping corrupted tail at offset 4096"
   → Discard records #3 and beyond
6. Server ready with records #1, #2 only

Data loss: 1 record
Recovery time: 500ms
```

### Recovery
```python
# Automatic (RedisLite handles it)
- Detects CRC mismatch
- Skips corrupted record
- Continues replaying
- Logs offset of corruption

# Manual (if needed)
1. Stop server
2. Backup corrupted WAL: cp data/aof.wal data/aof.wal.corrupt
3. Truncate WAL: truncate -s 0 data/aof.wal
4. Delete or restore snapshot: cp data/dump.json.bak data/dump.json
5. Restart server
```

### Prevention
```bash
# Monitor WAL size (grows indefinitely)
ls -lh data/aof.wal

# Rotate WAL monthly
REDISLITE_AOF_FSYNC_POLICY=always  # Safer writes

# Enable compression
gzip data/aof.wal  # After backup
```

### Why This Happens
- **Power failure mid-write**: 1-10% of write operations
- **Filesystem error**: Bad sector on disk
- **Process crash**: SIGKILL during buffer flush
- **Kernel bug**: Rare, but OS can corrupt data

---

## 5. Slow Disk / High I/O

### Symptoms
- Latency p99 goes from 100µs to 10ms
- Throughput drops from 45k ops/sec to 5k ops/sec
- CPU remains low (waiting on disk)
- fsync_policy = "always" (worst case)

### Behavior During Slow Disk
```
Disk speed: Normal 1ms per fsync
                   ↓ (disk degrades)
Disk speed: Slow 10ms per fsync (10x!)

Write path before:
parse (3µs) + lock (5µs) + memory (2µs) + fsync (1000µs) = 1010µs

Write path after slow disk:
parse (3µs) + lock (5µs) + memory (2µs) + fsync (10000µs) = 10010µs

Client sees: 10ms latency (10x worse!)
```

### Backpressure Engagement
```python
# When fsync takes > 10ms:
if fsync_time > 10ms:
    # Backpressure: Slow clients down
    if queue_depth > 1000:
        return -ERR Server busy, too many pending operations
        # Clients back off, reduce load
```

### Monitoring
```bash
# Check disk speed
fio --name=random-read --ioengine=libaio --rw=randread \
    --bs=4k --direct=1 --size=1G

# Typical: 1-2ms latency
# Degraded: 5-50ms latency
# Very bad: 100ms+
```

### Recovery
```
1. Immediate: Switch to fsync_policy="no" (risky)
   SET fsync_policy no
   
2. Short-term: Switch to fsync_policy="everysec"
   SET fsync_policy everysec
   
3. Long-term: Move to faster disk
   - Replace HDD with SSD
   - Move to local NVMe
   - Use disk controller with write-back cache

4. Monitoring: Alert if p99 latency > 5ms
```

### Mitigation
- Use SSD (mandatory for production)
- Enable disk write-back cache
- Separate AOF and snapshot to different disks
- Implement request batching (fsync fewer times)

---

## 6. Process Crash (SIGKILL, OOM, Segfault)

### Symptoms
- Unexpected restart
- Partial writes may be lost
- Client connections dropped
- Server restarts with persisted data

### Behavior During Crash
```
Normal operation → SIGKILL received → Process terminates immediately

Kernel action:
- Flush file buffers (unless fsync_policy="no")
- Close all sockets
- Release memory

RedisLite actions:
- None (process is dead)

Recovery (automatic on restart):
1. Load snapshot: dump.json (last 30s checkpoint)
2. Replay WAL: aof.wal (since last snapshot)
3. Verify data integrity (CRC checks)
4. Server ready

Data recovered: 99.99%
Data lost: Last 1-30 seconds (if fsync="everysec")
Time to recovery: 500ms - 5s
```

### Prevention
- Run inside container with restart policy: `restart: always`
- Monitor process health: Watch for crashes
- Set up system resource limits
- Use memory limiting cgroup

### Monitoring
```bash
# Check for recent crashes
journalctl -u redislite -n 50

# Set up alerting
if process_restart_count > 5 in 1_hour:
    alert_frequent_crashes
    check_logs for OOM
```

---

## 7. Port Already in Use

### Symptoms
- Startup fails immediately
- Error: "Address already in use"
- Previous instance didn't shut down cleanly

### Behavior
```
Process A listening on :6379
Process A crashes (but doesn't release port)
Process B tries to start on :6379
→ OSError: [Errno 48] Address already in use

Recovery:
1. Immediate: Kill old process
   lsof -i :6379
   kill -9 <pid>
   
2. Wait: Let OS release port (2-60s, TCP TIME-WAIT)
   
3. Restart: Process B can now bind
```

### Prevention
- Set SO_REUSEADDR socket option (already done)
- Use systemd Type=notify for clean shutdown
- Implement SIGTERM handler

---

## 8. Configuration Mismatch (Replication)

### Symptoms
- Replica won't sync
- "Configuration mismatch" in logs
- Master and replica have different settings

### Behavior
```
Master config:
  max_memory_mb = 100
  eviction_policy = lru

Replica config:
  max_memory_mb = 50  ← DIFFERENT!
  eviction_policy = none

Sync problem:
- Master sends SET commands for 100MB data
- Replica can only hold 50MB
- Replica evicts, data is inconsistent
- No alerts (silent data loss!)
```

### Prevention
```bash
# Use same config for all replicas
cat > redislite-master.conf
REDISLITE_MAX_MEMORY_MB=100
REDISLITE_EVICTION_POLICY=lru
REDISLITE_MAX_KEYS=1000000

# Copy to replicas
scp redislite-master.conf replica1:/etc/redislite/redislite.conf
scp redislite-master.conf replica2:/etc/redislite/redislite.conf
```

### Monitoring
```bash
# Compare configs on startup
redis-cli CONFIG GET maxmemory
# Should match on master and replicas
```

---

## 9. Connection Limit Exceeded

### Symptoms
- New connections refused
- "Connection refused" error
- Existing clients work fine
- Metrics show connections=1000 (at limit)

### Behavior
```
max_clients = 1000 (configured)

Connection #1000: Established ✓
Connection #1001: REJECTED
  → -ERR Too many clients connected
  
Clients experiencing this:
- Load balancer health checks fail
- New user sessions can't connect
- Existing sessions work (not disconnected)
```

### Recovery
```python
# Increase limit (if hardware supports)
SET max_clients 2000

# Or reduce existing clients
# Kill idle connections > 5 minutes
redis-cli TIMEOUT 300  # (not implemented, manual)

# Monitor
redis-cli INFO stats | grep connected_clients
```

### Mitigation
- Set max_clients based on ulimit
- Implement connection pooling on client
- Monitor connection count continuously
- Alert when connections > max_clients * 0.8

---

## 10. Clock System Change (Time Jump)

### Symptoms
- TTL behavior strange
- Keys expire early or never
- Replication lag suddenly increases

### Behavior
```
System clock: 2024-02-27 10:00:00
Key set with: TTL 3600s → expires at 10:01:00

System clock jumps forward: 2024-02-27 11:00:00 (+1 hour)

Monotonic clock protection:
- Monotonic time: 1000000.000s
- TTL expiry: 1003600.000s (monotonic + 3600)
- Key NOT affected by system time jump ✓

Result: Key still valid (expires at monotonic 1003600)
✓ Monotonic clock prevents corruption
```

---

## Summary: Failure Mode Handling

| Mode | Severity | Recovery | Prevention |
|------|----------|----------|-----------|
| Disk Full | HIGH | Manual + AOF rotation | Monitor df |
| OOM | HIGH | Eviction or restart | TTL + monitoring |
| Replica Disconnect | MEDIUM | Auto-reconnect | Check network |
| Corrupted WAL | MEDIUM | Skip corrupted tail | Periodic backup |
| Slow Disk | MEDIUM | Switch fsync policy | Use SSD |
| Process Crash | MEDIUM | Auto-restart | Container restart |
| Port in Use | LOW | Kill old process | SO_REUSEADDR |
| Config Mismatch | LOW | Manual fix | Test configs |
| Connection Limit | LOW | Increase limit | Monitor |
| Clock Jump | LOW | Monotonic time | Already handled |

---

## Observability Checklist

```
[ ] Monitor disk space (alert > 80%)
[ ] Monitor memory usage (alert > 90%)
[ ] Monitor replication lag (alert > 10s)
[ ] Monitor error rate (alert > 1%)
[ ] Monitor connection count (alert > 80%)
[ ] Monitor p99 latency (alert > 5ms)
[ ] Monitor eviction rate (alert > 1000/sec)
[ ] Check WAL file size (alert if > 1GB)
[ ] Verify snapshot timing (every 30s ± 5s)
[ ] Test crash recovery quarterly
```

This is how production databases are operated.
