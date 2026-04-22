# Pitch Script — Meta PyTorch OpenEnv Hackathon 2026

**Speaker:** Arjun Madhava  
**Target time:** 3 minutes exactly (practice until delivery is 2:55–3:05)  
**Format:** In-person, judges in front of you. Slides or live demo optional.

---

## DELIVERY NOTES

- Speak at **140–150 words per minute** — conversational, not rushing.
- Make **eye contact** with each judge for 2–3 seconds before moving on.
- **Pause** after "The problem is X." Let it land.
- Use your hands to gesture toward the screen when referencing the demo.
- Do not read from this script. Use it to rehearse. Know the beats, not the words.

---

## [0:00 – 0:30] HOOK: The Real Problem

*[Start standing, calm, slight smile. Do not rush this.]*

> "Walk into any fulfilment center today and you'll see robots that are fast — but brittle.
>
> Give them a structured task: they execute it perfectly.
> Change the instruction mid-run? The robot stops and waits for a human.
>
> That's not a hardware problem. That's a **planning** problem.
> And it's exactly the gap this project closes."

*[Pause. Let the setup land.]*

---

## [0:30 – 1:30] THE ENVIRONMENT: What Makes It Hard

*[Start moving — if there's a screen, point to it briefly.]*

> "I built an OpenEnv-compliant warehouse environment where an AI agent receives **natural-language orders** — not JSON, not a structured API call — and turns them into efficient action sequences.
>
> An order looks like this: *'Pick the foam insert first, then the fragile sensor — it needs the foam for protection. Deliver to Staging Zone 2 before the deadline. The sensor is priority.'*
>
> The agent has to parse that instruction, resolve the dependencies, plan the route, handle the deadline — and then do it again for the next order in the queue.
>
> There are four task tiers, scaling from a simple 5x5 grid to a 15x15 grid with five concurrent orders, dynamic arrivals, and occasional stock shortages.
>
> And for the finale, I added a fifth task: **two robots, shared queue, collision avoidance**. A genuine multi-agent episode."

*[Beat. This is the transition.]*

---

## [1:30 – 2:15] RESULTS: Evidence of Learning

*[Calm down your energy slightly. Evidence section should feel grounded.]*

> "The agent is trained using PyTorch DQN with curriculum progression — starting from simple orders, advancing to the hardest tier only when performance is consistently above 0.8.
>
> After 2000 episodes, here's what the training curve shows:
>
> Episode score went from a **random policy baseline of 0.15** to a **trained average of 0.64** — that's a 327% improvement.
>
> Orders completed per episode went from 1.2 out of 5 to 3.8 out of 5.
>
> Steps to complete an order dropped by 60%.
>
> This is not curve fitting. The agent learned to respect dependency chains, respect deadlines, and balance workload — because the reward function penalises each failure mode independently."

---

## [2:15 – 2:45] WHY IT MATTERS

*[Pick up energy slightly. This is where you connect to the bigger picture.]*

> "I chose warehouse coordination not because of the market size — though it's a 50 billion dollar problem — but because it forces you to get three things right simultaneously:
>
> First: **natural language as the interface**. Operators should not need to write JSON to give a robot instructions.
>
> Second: **long-horizon planning under constraints**. Dependencies, deadlines, priorities — real orders have all three.
>
> Third: **self-improvement in deployment**. The system uses episode memory to feed recent failure patterns back into the planner. It gets better without being retrained from scratch.
>
> These three properties are not unique to warehouses. They show up in every agentic system that has to operate in a messy, instruction-driven real world."

---

## [2:45 – 3:00] CLOSE

*[Slow down. Confident, not rushed.]*

> "The code is open-source, fully OpenEnv-compliant, and deployed on Hugging Face Spaces.
>
> Thank you."

*[Hold eye contact. Do not immediately look away. Wait for the Q&A.]*

---

## Q&A PREP — Likely Questions

| Question | Answer |
|---|---|
| "How did you validate the results?" | "Training plots show the learning curve across 2000 episodes. Before/after score comparison is in metrics.json in the repo. 12 unit tests cover reward logic, parser, and environment." |
| "Can it generalize?" | "Obstacles and item positions are randomized per episode. The curriculum forces the agent to handle four increasing difficulty levels. The reward function is task-agnostic — the same function grades all five tasks." |
| "What's next?" | "Multi-robot training with a shared policy vs. independent policies — does coordination emerge without explicit reward shaping? That's the interesting next question." |
| "Why not a pure LLM?" | "The LLM plans; the algorithmic reward judges. Letting the LLM touch the reward creates evaluation drift — you can't compare runs. Separating them keeps results reproducible." |
| "Can we see it run?" | "Yes — either the HF Spaces demo or a local run: uvicorn to start the server, then python inference.py. I can show you the grid render right now if you'd like." |
| "Why warehouse?" | "It's the simplest setting where you need all three properties at once: NL parsing, long-horizon planning, and self-improvement. Solve it cleanly here and the architecture transfers." |

---

## PRACTICE LOG

Track each rehearsal below:

| Take | Time | Notes |
|---|---|---|
| 1 | __ : __ | |
| 2 | __ : __ | |
| 3 | __ : __ | |
| 4 | __ : __ | |
| 5 | __ : __ | Target: 2:55–3:05 |

**Success criterion:** Delivery sounds natural, not read, in under 3:05.

---

*Arjun Madhava | Meta PyTorch OpenEnv Hackathon 2026 | April 25-26, Bangalore*
