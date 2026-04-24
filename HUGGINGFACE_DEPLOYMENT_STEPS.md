# 🚀 HuggingFace Spaces Deployment Guide

## Step 1: Create HF Spaces Repository

### Option A: Via Web Interface (Recommended)
1. Go to https://huggingface.co/spaces
2. Click **"Create new Space"**
3. Enter repository name: `warehouse-env` (or your preferred name)
4. Choose space type: **Docker**
5. Select visibility: **Public** (for hackathon submission)
6. Click **"Create Space"**

### Option B: Via Command Line
```bash
# Clone the HF Spaces repo template (after creating on web)
git clone https://huggingface.co/spaces/YOUR_USERNAME/warehouse-env
cd warehouse-env
```

---

## Step 2: Prepare Files for Deployment

**Files needed in HF Spaces repo:**
- ✅ `Dockerfile` (already ready)
- ✅ `requirements.txt` (just created)
- ✅ `app.py` (just created in root)
- ✅ `warehouse_env/` (entire directory)

---

## Step 3: Push Code to HF Spaces

### Via Git (Command Line Method)

```powershell
# Navigate to workspace directory
cd c:\Users\smart\OneDrive\Desktop\Hackathons\meta

# Configure git for HF (if first time)
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# Add HF Spaces remote (after creating space on web)
git remote add huggingface https://huggingface.co/spaces/YOUR_USERNAME/warehouse-env

# Push to HF Spaces
git push huggingface main --force
```

**Replace `YOUR_USERNAME` with your actual HuggingFace username**

---

## Step 4: Monitor Deployment

1. Go to your HF Spaces page: `https://huggingface.co/spaces/YOUR_USERNAME/warehouse-env`
2. Watch the "Building" section for logs
3. Wait for status to change from "Building" → "Running"
4. Typical build time: 5-15 minutes

**What to look for in logs:**
- ✅ `Sending build context to Docker daemon`
- ✅ `Step 1/N : FROM python:3.11-slim`
- ✅ `Successfully installed [all packages]`
- ✅ `Container successfully built`

---

## Step 5: Test Live Instance

Once deployment is complete:

1. Navigate to your Space URL (HF provides it after build completes)
2. You should see: `{"status": "ok", "message": "OpenEnv Warehouse Logistics API running."}`
3. Test WebSocket connection:

```powershell
# From your local machine, test connection to live instance
$env:API_BASE_URL="https://YOUR_USERNAME-warehouse-env.hf.space"

# Or test with Python
python -c "
import asyncio
import aiohttp

async def test():
    async with aiohttp.ClientSession() as session:
        async with session.get('https://YOUR_USERNAME-warehouse-env.hf.space/') as r:
            print(await r.json())

asyncio.run(test())
"
```

---

## Step 6: Get Shareable Live URL

**Your HF Spaces public URL:**
```
https://huggingface.co/spaces/YOUR_USERNAME/warehouse-env
```

**Embedded interface URL:**
```
https://YOUR_USERNAME-warehouse-env.hf.space
```

**Save this URL for submission!**

---

## Troubleshooting

### Issue: Build Fails
**Check logs for:**
- Missing Python dependencies (add to requirements.txt)
- Port binding errors (should use 7860)
- Path issues (PYTHONPATH set in Dockerfile)

**Fix:** Update file, recommit with `git push huggingface main --force`

### Issue: WebSocket Connection Fails
**Ensure:**
- Dockerfile EXPOSE line shows: `EXPOSE 7860`
- app.py uses: `host="0.0.0.0", port=7860`
- HF Spaces allows WebSocket (it does by default)

### Issue: Slow Build
- HF Spaces often takes 10-20 minutes for first build
- Wait for "Running" status before testing
- Check build logs for dependency installation time

---

## Success Criteria

✅ HF Spaces page shows "Running" status  
✅ Root endpoint (`/`) returns `{"status": "ok", ...}`  
✅ URL is publicly accessible  
✅ WebSocket connection works from external network  
✅ URL ready for hackathon submission  

---

## Next: Record Video

After deployment succeeds, proceed to video recording using the guide below.
