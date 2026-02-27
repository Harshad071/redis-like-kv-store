# Deployment Guide - RedisLite Microservice

This guide covers deploying the RedisLite Microservice to various platforms.

## Table of Contents

1. [Vercel Deployment](#vercel-deployment)
2. [Docker Deployment](#docker-deployment)
3. [AWS Deployment](#aws-deployment)
4. [Development Deployment](#development-deployment)

---

## Vercel Deployment

### Prerequisites
- Vercel account (https://vercel.com)
- GitHub account
- Project pushed to GitHub

### Step-by-Step Deployment

#### Option 1: Using Vercel Dashboard

1. **Sign in to Vercel**
   - Go to https://vercel.com/dashboard
   - Click "New Project"

2. **Import GitHub Repository**
   - Click "Import Project"
   - Paste your GitHub repository URL or select from your repositories
   - Click "Continue"

3. **Configure Project**
   - Project Name: Enter your project name
   - Framework: Select "Other"
   - Root Directory: Leave as is (./api is auto-detected)
   - Environment Variables: None required for basic use

4. **Deploy**
   - Click "Deploy"
   - Wait for deployment to complete
   - Your API will be available at `https://<project-name>.vercel.app`

5. **Test Your Deployment**
   ```bash
   # Check health
   curl https://<project-name>.vercel.app/health
   
   # Set a key
   curl -X POST https://<project-name>.vercel.app/api/set \
     -H "Content-Type: application/json" \
     -d '{"key": "test", "value": "success"}'
   
   # Get a key
   curl https://<project-name>.vercel.app/api/get?key=test
   ```

#### Option 2: Using Vercel CLI

1. **Install Vercel CLI**
   ```bash
   npm i -g vercel
   ```

2. **Login to Vercel**
   ```bash
   vercel login
   ```

3. **Deploy**
   ```bash
   vercel
   ```

4. **Follow the prompts**
   - Confirm project name
   - Set root directory (if needed)
   - Choose to link existing project or create new

### Vercel Environment Variables

To add environment variables:

1. Go to your project settings in Vercel dashboard
2. Navigate to Settings → Environment Variables
3. Add any custom environment variables (optional)

Example:
```
API_VERSION=1.0.0
LOG_LEVEL=info
```

### Vercel Monitoring

After deployment:

1. **View Logs**
   - Go to Deployments tab
   - Click on latest deployment
   - View build logs and runtime logs

2. **Monitor Performance**
   - Go to Analytics tab
   - Monitor request counts and response times

3. **Custom Domain** (Optional)
   - Go to Settings → Domains
   - Add your custom domain
   - Configure DNS records

---

## Docker Deployment

### Local Docker

1. **Build Image**
   ```bash
   docker build -t redislite-api:latest .
   ```

2. **Run Container**
   ```bash
   docker run -p 8000:8000 redislite-api:latest
   ```

3. **Test**
   ```bash
   curl http://localhost:8000/health
   ```

### Docker Compose

1. **Start Services**
   ```bash
   docker-compose up -d
   ```

2. **View Logs**
   ```bash
   docker-compose logs -f redislite-api
   ```

3. **Stop Services**
   ```bash
   docker-compose down
   ```

### Docker Registry (Docker Hub)

1. **Build and Tag**
   ```bash
   docker build -t yourusername/redislite-api:latest .
   ```

2. **Login to Docker Hub**
   ```bash
   docker login
   ```

3. **Push Image**
   ```bash
   docker push yourusername/redislite-api:latest
   ```

### Docker on Cloud Platforms

#### Google Cloud Run
```bash
gcloud run deploy redislite-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

#### AWS ECS
```bash
# Create ECR repository
aws ecr create-repository --repository-name redislite-api

# Tag and push image
docker tag redislite-api:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/redislite-api:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/redislite-api:latest

# Deploy to ECS (configure task definition and service)
```

---

## AWS Deployment

### AWS Lambda + API Gateway

1. **Prepare Function**
   ```bash
   pip install -r requirements.txt -t lambda_package/
   cp -r api/* lambda_package/
   cd lambda_package && zip -r ../function.zip . && cd ..
   ```

2. **Create Lambda Function**
   - Go to AWS Lambda console
   - Create new function
   - Upload `function.zip` as code
   - Runtime: Python 3.11
   - Timeout: 30 seconds
   - Memory: 512 MB or more

3. **Create API Gateway**
   - Create new API (REST API)
   - Create resources for each endpoint
   - Configure Lambda integration
   - Deploy API stage

4. **Test**
   ```bash
   curl https://<api-gateway-url>/prod/health
   ```

### AWS App Runner

1. **Push to ECR**
   ```bash
   aws ecr create-repository --repository-name redislite-api
   docker build -t <account>.dkr.ecr.us-east-1.amazonaws.com/redislite-api .
   docker push <account>.dkr.ecr.us-east-1.amazonaws.com/redislite-api
   ```

2. **Create App Runner Service**
   - Go to AWS App Runner
   - Create new service
   - Select ECR as source
   - Configure and deploy

---

## Development Deployment

### Local Development

1. **Create Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Development Server**
   ```bash
   uvicorn api.index:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Access**
   - API: http://localhost:8000
   - Docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

### Local Testing

```bash
# Test using Python client
python -c "
from api.client import RedisLiteClient
with RedisLiteClient('http://localhost:8000') as client:
    print(client.health())
    print(client.set('key', 'value'))
    print(client.get('key'))
"

# Test using curl
curl -X POST http://localhost:8000/api/set \
  -H "Content-Type: application/json" \
  -d '{"key": "test", "value": "hello"}'

curl http://localhost:8000/api/get?key=test
```

---

## Performance Considerations

### For Vercel Deployment
- Memory: ~128MB base + data size
- Timeout: 60 seconds (Pro) or 10 seconds (free)
- Cold start: ~500ms-1s
- Best for: Caching, session management, rate limiting

### For Docker Deployment
- Memory: Configurable (256MB minimum recommended)
- CPU: Scales with allocation
- No cold starts (always running)
- Best for: Production, dedicated infrastructure

### Optimization Tips
1. **Data Size**: Keep values < 1MB each
2. **TTL Usage**: Set appropriate TTLs to manage memory
3. **Connection Pooling**: Reuse client connections
4. **Caching**: Cache client instance when possible

---

## Monitoring and Logging

### Vercel
- Logs available in dashboard
- Monitor API usage in Analytics
- Set up alerts for errors

### Docker
```bash
# View logs
docker logs <container-id>

# Stream logs
docker logs -f <container-id>

# Inspect container
docker inspect <container-id>
```

### Application
- Check `/health` endpoint regularly
- Monitor response times
- Track error rates
- Log requests to external service if needed

---

## Troubleshooting

### Deployment Issues

**Issue**: Deployment fails on Vercel
- Solution: Check `vercel.json` configuration
- Ensure `requirements.txt` is in root directory

**Issue**: Cold start is too slow
- Solution: This is normal for Vercel (~1s)
- Consider Docker for consistent performance

**Issue**: Data lost after deployment
- Solution: This is expected with serverless
- Use persistent database for long-term storage

**Issue**: API returns 404
- Solution: Check endpoint URLs match documentation
- Verify deployment is successful

---

## Security Best Practices

1. **HTTPS Only**: Use HTTPS in production
2. **CORS**: Configure for your domain
3. **Rate Limiting**: Implement in API Gateway or proxy
4. **Authentication**: Add API key validation if needed
5. **Data Validation**: Always validate input
6. **Secrets**: Use environment variables for sensitive data

---

## Cost Considerations

### Vercel
- Free tier: $0 (with limitations)
- Pro: $20/month
- Enterprise: Custom pricing
- Charges for compute time and storage

### Docker on Cloud
- Google Cloud Run: Pay per request (~$0.40 per 1M)
- AWS ECS: From $0.32/day
- AWS Lambda: $0.50 per 1M invocations

### Budget Optimization
- Use free tier for development/testing
- Monitor API usage patterns
- Clean up expired data regularly
- Use appropriate instance sizes

---

For more help, refer to the main [README.md](README.md) or check platform-specific documentation.
