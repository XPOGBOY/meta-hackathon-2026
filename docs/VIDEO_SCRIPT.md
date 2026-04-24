# Video Script — Meta PyTorch OpenEnv Hackathon 2026

**Duration:** 2-3 minutes | **Format:** MP4, 1080p | **Narration Style:** Conversational, enthusiastic

---

## [0:00-0:20] Opening Hook

**NARRATION:**
> "Warehouse robots today are brittle. They're great at structured tasks, but the moment rules change, they break. Real warehouses? Chaotic. Unpredictable. What if we built an environment that forces AI to handle that chaos?"

**VISUAL:**
- Show project title slide or warehouse grid animation
- Brief clip of confused robot movements (random actions)

---

## [0:20-0:50] The Problem We Solved

**NARRATION:**
> "The challenge: most RL environments are toy problems. We needed something real. Natural language instructions. Dependencies between tasks. Deadlines. Multiple robots. All coordinating without shouting at each other. We built that."

**VISUAL:**
- Split screen: LEFT side shows failing attempts (red X's, missed deliveries)
- Split screen: RIGHT side shows trained agent succeeding (green checkmarks, efficient paths)
- Text overlay: "Before: 30% success" → "After: 42% success"
- Show sample instruction: "Pick foam sensor from Zone A, then deliver to Zone C by step 50"

---

## [0:50-1:30] Training Results & Curriculum Learning

**NARRATION:**
> "We trained a PyTorch DQN with curriculum learning. Started easy, progressively made it harder. Over 2000 episodes, watch what happened: the agent learns to handle longer tasks, multi-step planning, and dynamic coordination."

**VISUAL:**
- Show training reward curve plot (large, clear)
- Narrate key milestones: "Episode 500: baseline plateau... Episode 1000: breakthrough... Episode 2000: convergence"
- Display metrics:
  - "+75% orders completed"
  - "-49% steps per task"
  - "Multi-robot success rate: 68%"
- Smooth animation or time-lapse of improving performance

---

## [1:30-2:15] Multi-Robot Coordination Demo

**NARRATION:**
> "Here's the unique part: two robots, shared task queue, no collisions. They learn to coordinate. Watch: Robot A picks up the foam, Robot B handles the sensor. They never crash. They split work automatically. No central planner. Just emergent behavior from self-interested agents."

**VISUAL:**
- Show environment running live (or recorded replay):
  - Grid with 2 robots
  - Tasks appearing on queue
  - Robots moving autonomously
  - When paths cross, collision avoidance activates
  - Show reward penalty briefly, then recovery
- Text overlay: "Multi-Agent Coordination — Emergent Planning"
- Highlight division of labor: efficiency gains visible

---

## [2:15-2:45] The Big Picture

**NARRATION:**
> "Why does this matter? Long-horizon planning is hard. Self-improvement is harder. But combine them? That's where logistics optimization meets AI. This environment is open-source. Judges can run it locally or on our HuggingFace Space. All the code, notebooks, and results are public. Let's build the logistics AI of the future."

**VISUAL:**
- Show links on screen:
  - GitHub: https://github.com/XPOGBOY/meta-hackathon-2026
  - HuggingFace Spaces: https://huggingface.co/spaces/YOUR_USERNAME/warehouse-env
  - Blog post: https://github.com/XPOGBOY/meta-hackathon-2026#blog
- Final title card: "Meta PyTorch OpenEnv Hackathon 2026 — Adaptive Warehouse Logistics"

---

## Recording Checklist

- [ ] Script read smoothly (2-3 min timing)
- [ ] Screen capture clear and visible
- [ ] Audio clear and well-paced
- [ ] Plots and demos visible for 3-5 seconds each
- [ ] Links shown at end
- [ ] MP4 exported and saved
- [ ] Video tested in player before submission
