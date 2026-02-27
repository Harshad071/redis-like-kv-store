# RedisLite Quick Start

Get RedisLite running in 5 minutes.

## Option 1: Local (Python)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
uvicorn api.index:app --host 0.0.0.0 --port 8000

# Output:
# Uvicorn running on http://0.0.0.0:8000
# TCP server listening on 0.0.0.0:6379
```

## Option 2: Docker

```bash
# 1. Build
docker build -t redislite .

# 2. Run
docker run -p 6379:6379 -p 8000:8000 redislite

# Or with docker-compose
docker-compose up
```

## Option 3: Railway (Production)

```bash
# 1. Connect GitHub repo
# 2. Railway auto-detects Dockerfile
# 3. Add environment variables in dashboard:
#    - REDISLITE_MAX_MEMORY_MB=200
#    - REDISLITE_LOG_LEVEL=INFO
# 4. Deploy (automatic)
```

---

## Test It

### Using redis-cli
```bash
redis-cli -p 6379

# Commands
> PING
PONG

> SET mykey "Hello World"
OK

> GET mykey
"Hello World"

> EXPIRE mykey 10
(integer) 1

> TTL mykey
(integer) 9
```

### Using curl (HTTP)
```bash
# Set
curl -X POST http://localhost:8000/api/set \
  -H "Content-Type: application/json" \
  -d '{"key": "test", "value": "data", "ttl": 60}'

# Get
curl http://localhost:8000/api/get/test

# Info
curl http://localhost:8000/api/info

# Metrics
curl http://localhost:8000/api/metrics
```

### Using Python
```python
import redis

# Connect
r = redis.Redis(host='localhost', port=6379)

# Use
r.set('key', 'value')
print(r.get('key'))  # b'value'
r.expire('key', 60)
print(r.ttl('key'))  # ~60
```

---

## Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/set` | POST | Set key with optional TTL |
| `/api/get/{key}` | GET | Get value |
| `/api/delete/{key}` | DELETE | Delete key |
| `/api/exists/{key}` | GET | Check if exists |
| `/api/ttl/{key}` | GET | Get remaining TTL |
| `/api/keys` | GET | List keys |
| `/api/info` | GET | Server statistics |
| `/api/metrics` | GET | Prometheus metrics |
| `/api/flushdb` | POST | Delete all keys |
| `/api/dbsize` | GET | Key count |
| `/health` | GET | Health check |

---

## Configuration

Create `.env` file:

```bash
REDISLITE_TCP_PORT=6379
REDISLITE_HTTP_PORT=8000
REDISLITE_MAX_MEMORY_MB=100
REDISLITE_EVICTION_POLICY=lru
REDISLITE_PERSISTENCE_ENABLED=true
REDISLITE_LOG_LEVEL=INFO
```

Or use defaults (see `.env.example`).

---

## Monitor

Watch metrics in real-time:

```bash
# Every 2 seconds
watch -n 2 'curl -s http://localhost:8000/api/metrics | head -20'
```

Or import to Grafana:
1. Add Prometheus datasource: `http://localhost:8000`
2. Create dashboard with `redislite_*` metrics

---

## Benchmark

```bash
python benchmarks/benchmark.py
```

Runs 7 test scenarios (100k+ operations) and outputs:
- Throughput (ops/sec)
- Latency percentiles (p50, p95, p99)
- Memory usage
- Results saved to `benchmark_results.json`

---

## Persistence

Data automatically persists:
- `./data/aof.log` - Every command logged (durability)
- `./data/dump.json` - Full snapshot every 30s (recovery)

On restart, server automatically recovers from latest snapshot + AOF replay.

---

## Next Steps

1. **Read**: `docs/ARCHITECTURE.md` (design details)
2. **Deploy**: `PRODUCTION_README.md` (deployment guides)
3. **Configure**: `.env.example` (all options)
4. **Monitor**: `/api/info` and `/api/metrics`
5. **Scale**: Add replicas for read scaling

---

## Need Help?

- **Troubleshooting**: See PRODUCTION_README.md
- **Design**: See docs/ARCHITECTURE.md
- **Benchmarks**: Run `python benchmarks/benchmark.py`
- **Logs**: Check stdout or logs in deployment platform

---

**Ready to go!** Start the server and access it at:
- TCP: `localhost:6379` (redis-cli)
- HTTP: `http://localhost:8000` (curl)
- Metrics: `http://localhost:8000/api/metrics` (Prometheus)
- Docs: `http://localhost:8000/docs` (Swagger UI)
