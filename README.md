# RedisLite Microservice

A production-ready, serverless HTTP API wrapper for RedisLite - an in-memory key-value store with TTL support. Deployed on Vercel for lightning-fast, scalable operations.

## Features

- **In-Memory Key-Value Store**: Fast, thread-safe storage with automatic expiration
- **TTL Support**: Set expiration times for keys with automatic cleanup
- **RESTful API**: Simple HTTP endpoints for all operations
- **FastAPI**: Modern, async Python framework with auto-generated documentation
- **Serverless Ready**: Optimized for Vercel deployment
- **CORS Enabled**: Ready for cross-origin requests
- **Health Check**: Built-in monitoring endpoint

## Quick Start

### Local Development

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Run the development server**:
```bash
uvicorn api.index:app --reload
```

3. **Access the API**:
   - Interactive docs: `http://localhost:8000/docs`
   - ReDoc: `http://localhost:8000/redoc`
   - Health: `http://localhost:8000/health`

## API Endpoints

### Health Check
```
GET /health
```
Returns service status and version.

### Set a Key
```
POST /api/set
Content-Type: application/json

{
  "key": "user:123",
  "value": {"name": "John", "email": "john@example.com"},
  "ttl": 3600
}
```

**Response**:
```json
{
  "success": true,
  "key": "user:123",
  "ttl": 3600,
  "message": "Key set successfully"
}
```

### Get a Key
```
GET /api/get?key=user:123
```

**Response**:
```json
{
  "key": "user:123",
  "value": {"name": "John", "email": "john@example.com"},
  "exists": true
}
```

### Delete a Key
```
DELETE /api/delete?key=user:123
```

**Response**:
```json
{
  "key": "user:123",
  "deleted": true
}
```

### Check if Key Exists
```
GET /api/exists?key=user:123
```

**Response**:
```json
{
  "key": "user:123",
  "exists": true
}
```

## Deployment on Vercel

### Prerequisites
- Vercel account (https://vercel.com)
- GitHub repository with this project

### Deploy Steps

1. **Push to GitHub**:
```bash
git add .
git commit -m "Initial commit: RedisLite microservice"
git push origin main
```

2. **Deploy to Vercel**:
   - Go to https://vercel.com/import
   - Select your GitHub repository
   - Click "Deploy"
   - Vercel will automatically detect the `vercel.json` configuration

3. **Access Your API**:
   - Your API will be available at `https://your-project.vercel.app`
   - Interactive docs at `https://your-project.vercel.app/docs`

### Environment Variables

The service requires no environment variables for basic functionality. Optional environment variables:

```
PYTHONUNBUFFERED=1  # Ensures Python output is unbuffered (set in vercel.json)
```

## Docker Deployment

Build and run with Docker:

```bash
# Build
docker build -t redislite-api .

# Run
docker run -p 8000:8000 redislite-api
```

## API Examples

### Using cURL

```bash
# Set a key
curl -X POST http://localhost:8000/api/set \
  -H "Content-Type: application/json" \
  -d '{"key": "mykey", "value": "myvalue", "ttl": 60}'

# Get a key
curl http://localhost:8000/api/get?key=mykey

# Delete a key
curl -X DELETE http://localhost:8000/api/delete?key=mykey

# Check if key exists
curl http://localhost:8000/api/exists?key=mykey
```

### Using Python

```python
import requests

base_url = "http://localhost:8000"

# Set a key
response = requests.post(f"{base_url}/api/set", json={
    "key": "session:abc123",
    "value": {"user_id": 1, "role": "admin"},
    "ttl": 3600
})
print(response.json())

# Get a key
response = requests.get(f"{base_url}/api/get", params={"key": "session:abc123"})
print(response.json())
```

### Using JavaScript

```javascript
const baseUrl = "http://localhost:8000";

// Set a key
await fetch(`${baseUrl}/api/set`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    key: "token:xyz",
    value: { access: "write", user: "john" },
    ttl: 7200
  })
});

// Get a key
const response = await fetch(`${baseUrl}/api/get?key=token:xyz`);
const data = await response.json();
console.log(data);
```

## Use Cases

- **Session Management**: Store user sessions with automatic expiration
- **Cache Layer**: Quick access to frequently requested data
- **Rate Limiting**: Track API call counts with TTL-based reset
- **Temporary Storage**: Store temporary data that needs automatic cleanup
- **Real-time Features**: Fast in-memory data for real-time applications
- **Queue Simulation**: Simple job queue implementation

## Performance

- **Sub-millisecond latency**: In-memory operations
- **Thread-safe**: Multiple concurrent requests handled safely
- **Automatic cleanup**: Background daemon removes expired keys every second
- **Scalable**: Handles thousands of keys efficiently

## Architecture

```
┌─────────────────────────────────────────┐
│         Vercel Serverless               │
│  ┌─────────────────────────────────┐   │
│  │  FastAPI Application            │   │
│  │  (HTTP Routing & Validation)    │   │
│  └─────────────────────────────────┘   │
│             ↓                           │
│  ┌─────────────────────────────────┐   │
│  │  RedisLite Store                │   │
│  │  (In-Memory K/V with TTL)       │   │
│  └─────────────────────────────────┘   │
│             ↓                           │
│  ┌─────────────────────────────────┐   │
│  │  Expiration Daemon              │   │
│  │  (Background Cleanup Thread)    │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

## Limitations

- **Serverless constraints**: Data persists only during function execution
- **Memory limited**: Bound by serverless environment memory limits
- **Single instance**: Each deployment is independent (no shared state across instances)
- **Cold starts**: Initial request may experience latency

For persistent storage needs, consider integrating with a database like PostgreSQL or a managed Redis service.

## Development

### Project Structure

```
.
├── api/
│   ├── index.py          # Main FastAPI application
│   └── redislite.py      # RedisLite implementation
├── requirements.txt       # Python dependencies
├── vercel.json           # Vercel configuration
├── Dockerfile            # Docker configuration
└── README.md             # This file
```

### Code Quality

The code follows Python best practices:
- Type hints for better IDE support and documentation
- Comprehensive docstrings
- Thread-safe operations with locks
- Proper error handling
- CORS middleware for cross-origin support

## License

MIT

## Support

For issues, questions, or contributions, please visit the GitHub repository.
