---
title: Meta Hackathon 2026
emoji: "🏢"
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# OpenEnv Warehouse Agent

This repository contains a warehouse logistics agent built for the Meta PyTorch Hackathon 2026.

The Hugging Face Space runs as a Docker Space and starts the FastAPI server from `warehouse_env.server.app`.

## Local run

Install dependencies:

```bash
pip install -r warehouse_env/requirements.txt
```

Start the server:

```bash
python -m uvicorn warehouse_env.server.app:app --host 127.0.0.1 --port 7860
```

Run the agent:

```bash
python inference.py
```
