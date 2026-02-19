# 🛠️ RedisLite – A Redis-like Key-Value Store

**RedisLite** is a lightweight, in-memory key-value store inspired by [Redis](https://redis.io/). Built for learning and experimentation, it supports basic key-value operations, TTL (time-to-live), persistence, and simple concurrency. Perfect for developers and students who want to understand how modern in-memory databases work under the hood.

---

## 🔹 Features

- **In-Memory Storage:** Ultra-fast key-value operations using efficient data structures.
- **Persistence:** Optional snapshot-based or append-only file persistence to save your data.
- **TTL Support:** Automatically expire keys after a specified time.
- **Data Types:** Strings, Lists, and Hash-like structures (basic).
- **Concurrency Safe:** Thread-safe operations for multi-threaded applications.
- **Simple CLI Interface:** Interact with the store via a command-line interface.
- **Easy API Integration:** Simple methods to integrate in Python/Java projects.

---

## ⚡ Why RedisLite?

- Learn how caching engines like Redis work internally.
- Understand memory management, data structures, and persistence strategies.
- Build a foundation for distributed systems, caching, and real-time applications.
- Showcase a production-grade system-level project in your portfolio.

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+** or **Java 11+** (depending on implementation)
- Git

### Installation

```bash
# Clone the repo
git clone https://github.com/yourusername/RedisLite.git
cd RedisLite

# For Python version
pip install -r requirements.txt

### Run CLI

```bash
python redislite.py
# or
java -jar RedisLite.jar

## 📝 Basic Usage

### Python Example

```python
from redislite import RedisLite

store = RedisLite()

# Set and Get
store.set("name", "Harshad")
print(store.get("name"))  # Output: Harshad

# TTL example
store.set("session", "abc123", ttl=10)  # expires in 10 seconds

# Delete a key
store.delete("name")

### CLI Example

```text
> SET user Harshad
OK
> GET user
Harshad
> DEL user
1
> SET temp 123 EX 5
OK
💡 Advanced Features (Optional / Roadmap)

Pub/Sub Messaging

Sharding & Clustering for distributed storage

LRU/LFU eviction policies

Transactions (MULTI/EXEC)

Lua scripting support

📂 Project Structure
RedisLite/
├── redislite.py        # Core Python implementation
├── cli.py              # Command-line interface
├── persistence.py      # Snapshot / AOF logic
├── tests/              # Unit tests
├── README.md
└── requirements.txt

✅ Contributing

Contributions are welcome!

Fork the repository

Create a branch (feature/awesome-feature)

Commit your changes

Open a Pull Request

📜 License

MIT License © 2026 Harshad Jadhav


