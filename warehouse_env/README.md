---
title: Meta Hackathon 2026
emoji: 🏢
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---
# OpenEnv Warehouse Agent - Meta PyTorch Hackathon 2026

Hey! This is my submission for the Meta PyTorch Hackathon. 

## How I Approached This Problem
At first, I tried to train a Deep Q-Network (DQN) with PyTorch since it sounded awesome for a robotics problem. But honestly? Waiting for an RL model to optimally converge for a small 10x10 deterministic grid was taking forever and felt like overkill. I ran into huge state-space representation issues (the item order kept messing up the network) and training it perfectly took way too much time.

So, I pivoted. I ripped out the RL stuff and built a mathematically optimal Breadth-First Search (BFS) combined with a Traveling Salesman Problem (TSP) permutation solver. It instantly guarantees the highest possible grade every single time.

## Challenges I Faced
1. **State Space Issues**: My first RL attempt failed massively. 
2. **WebSocket CORS**: Setting up the server properly using `create_fastapi_app` threw so many `403 Forbidden` errors until I finally figured out I needed to forcibly inject the `CORSMiddleware`. (Spent like an hour on this lol).

## How to Run This
I left the `Dockerfile` in there for the Hugging Face Spaces deployment, but if you want to run it locally:

Install everything with `pip install -r requirements.txt`. 

Start the OpenEnv server:
```bash
python -m uvicorn warehouse_env.server.app:app --host 127.0.0.1 --port 8002
```

Run my agent:
```bash
python -m warehouse_env.inference
```

**TODO**: If I keep working on this after the hackathon, I definitely want to revisit the PyTorch RL approach for stochastic grids, since TSP obviously won't scale if items spawn dynamically! But for now, this gets the perfect score.
