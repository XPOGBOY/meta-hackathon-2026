# HuggingFace Spaces Deployment Guide

**Project:** Adaptive Warehouse OpenEnv  
**Repository:** https://github.com/XPOGBOY/meta-hackathon-2026  
**Date:** April 23, 2026

---

## Step-by-Step HuggingFace Spaces Deployment

### 1. Create HuggingFace Space

1. Go to https://huggingface.co/spaces
2. Click **"Create new Space"**
3. Fill in details:
   - **Space name:** `warehouse-env` or `meta-hackathon-2026`
   - **License:** Apache 2.0 (or your preference)
   - **Space SDK:** Docker
   - **Visibility:** Public
4. Click **"Create Space"**

You'll get a page like: `https://huggingface.co/spaces/YOUR_USERNAME/warehouse-env`

### 2. Connect to GitHub

In your HuggingFace Space settings:

1. Click **"Settings"** (gear icon)
2. Scroll to **"Repository details"**
3. Under **"Repo URL"**, enter:
   ```
   https://github.com/XPOGBOY/meta-hackathon-2026
   ```
4. Click **"Sync with repo"** or **"Create webhook"**

This will:
- Clone your GitHub repo
- Build the Docker image automatically
- Deploy the server on HuggingFace infrastructure

### 3. Configure Environment Variables (if needed)

In Space **Settings → "Secrets and environment variables"**:

```
API_BASE_URL=ws://127.0.0.1:8000
TORCH_DEVICE=cpu
```

(These are optional; defaults should work)

### 4. Wait for Build

The Space will:
1. Clone from GitHub
2. Build Docker image (2-5 minutes)
3. Start server on port 7860
4. Show "Running ✓" when ready

Once running, your Space is live at:
```
https://huggingface.co/spaces/YOUR_USERNAME/warehouse-env
```

### 5. Test the Deployment

Click **"Iframe"** or **"API"** tab to see your running environment.

To test via WebSocket:
```python
from warehouse_env.client import WarehouseEnv

env = WarehouseEnv(base_url="wss://your-username-warehouse-env.hf.space")
result = env.reset(task_name="simple_order")
print(result.observation)
```

---

## Automatic Redeploy on Git Push

Once webhook is set up, every push to GitHub automatically:
1. Triggers HuggingFace to pull new code
2. Rebuilds Docker image
3. Restarts the server

No manual action needed!

---

## Verify Deployment

After Space is running, verify:

- [ ] Space is "Running" (green indicator)
- [ ] README displayed with quick results table
- [ ] Training plots visible in `docs/plots/`
- [ ] Server responds on WebSocket
- [ ] Space URL works: `https://huggingface.co/spaces/YOUR_USERNAME/warehouse-env`

---

## Add Space URL to Submission

Update `SUBMISSION_URLS.txt`:

```
HuggingFace Spaces (live demo):
  https://huggingface.co/spaces/YOUR_USERNAME/warehouse-env
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Build fails | Check Dockerfile syntax, verify requirements.txt |
| Port conflict | Port 7860 is standard for Spaces, should auto-resolve |
| GitHub sync not working | Verify GitHub URL is correct, try **"Manual restart"** |
| Slow startup | First build takes 2-5 min. Subsequent starts are faster |

---

**Time Estimate:** 5-10 minutes for setup + 5 minutes for build

**Your Space will be live at:** `https://huggingface.co/spaces/YOUR_USERNAME/warehouse-env`
