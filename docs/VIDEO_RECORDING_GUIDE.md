# Video Recording Guide — YouTube Submission

**Project:** Adaptive Warehouse OpenEnv  
**Video Duration:** 90 seconds (maximum 2 minutes)  
**Format:** MP4, 1080p, 60fps (optional)  
**Publishing:** YouTube (unlisted)  
**Date:** April 23, 2026

---

## Video Script & Storyboard

### [0:00-0:15] Opening Hook (15 seconds)
**Narration (read this):**
> "Warehouse robots today are brittle. They nail structured tasks but fail when rules change. Real warehouses are chaotic. What if we built an environment that forces AI to handle that chaos?"

**Visual:**
- Background: Rotating 3D warehouse visualization or grid animation
- Text overlay: "Adaptive Warehouse OpenEnv"
- Show: A robot confused on a grid (flailing movement)

---

### [0:15-0:45] Problem & Solution (30 seconds)
**Narration:**
> "The problem: most RL environments are toy problems. We needed something real. Something with natural language instructions, dependencies, deadlines, and multiple robots coordinating. We built that. And it works."

**Visual:**
- Split screen LEFT: Show random agent failing (missing items, wrong deliveries)
- Split screen RIGHT: Show trained agent succeeding (efficient movement)
- Text overlay: "Before: 30% success" → "After: 42% success"
- Show an order in natural language: "Pick foam first, then sensor..."

---

### [0:45-1:15] Training Results (30 seconds)
**Narration:**
> "We trained a DQN with curriculum learning for 2000 episodes. Here's what happened."

**Visual:**
- Show training_reward.png plot (large, visible)
- Point out: Baseline (red line), training starts low, climbs over time
- Overlay text: "+75% orders completed" ... "-49% steps per task"
- Smooth curve visible, curriculum transitions annotated
- Final metric: "Trained agent: 0.28 score"

---

### [1:15-1:45] Multi-Robot Demo (30 seconds)
**Narration:**
> "But here's what's different. We added multi-robot coordination. Two robots, shared queue, no collisions. They learn to coordinate without explicit commands."

**Visual:**
- Show environment running (if possible)
- Two robots moving on grid
- When paths cross, robots avoid each other (show penalty/recovery)
- Orders being assigned automatically
- Text: "Multi-Agent Coordination (NEW)"
- Highlight: 2 robots efficiently dividing work

---

### [1:45-2:00] Call-to-Action (15 seconds)
**Narration:**
> "This environment is open-source. Judges can run it locally or on our HuggingFace Space. Check the github repo for the full code, training notebooks, and results. Links below."

**Visual:**
- Show GitHub link: https://github.com/XPOGBOY/meta-hackathon-2026
- Show HF Spaces link: https://huggingface.co/spaces/XPOGBOY/warehouse-env
- Show Blog: https://github.com/XPOGBOY/meta-hackathon-2026#blog
- Final text: "Meta PyTorch OpenEnv Hackathon 2026"

---

## Recording Tools (Choose one)

### Option 1: OBS Studio (FREE, Recommended)
**Download:** https://obsproject.com/

**Setup:**
1. Install OBS
2. Click **"+"** under "Sources"
3. Select **"Display Capture"** (to record screen)
4. Start **"Recording"**
5. Perform actions on screen below (see "Actions" section)
6. Stop recording

**Output file:** Saved as `.mp4` in Documents folder

**Pros:** Free, professional, no watermark  
**Cons:** Slight learning curve

---

### Option 2: ScreenFlow (macOS only)
**Cost:** ~$30 (or free trial)

**Steps:**
1. Open ScreenFlow
2. Select recording area
3. Click Record
4. Perform actions
5. Stop and save

---

### Option 3: ShareX (Windows)
**Download:** https://getsharex.com/ (FREE)

**Steps:**
1. Install ShareX
2. Ctrl+Shift+R to start recording
3. Perform actions
4. Stop recording
5. Video saved

---

### Option 4: Windows 10/11 Game Bar
**Shortcut:** Windows Key + G

**Steps:**
1. Press Win+G
2. Click "Start recording"
3. Record screen
4. Stop when done
5. Video saved to Videos/Captures

---

## Actions to Perform (On Camera)

### Segment 1: Show Problem (0:00-0:15)
- Open terminal or command prompt
- Show command: `python inference.py`
- Let agent run briefly (show confused movements for ~5 seconds)
- Stop with Ctrl+C

### Segment 2: Show Results (0:15-0:45)
- Open file browser
- Navigate to `docs/plots/`
- Show `training_reward.png` (let camera focus on it for 10 seconds)
- Show metrics in `docs/plots/metrics.json` (open in text editor)
- Show `results/TRAINING_SUMMARY.md` (scroll through briefly)

### Segment 3: Show Trained Agent (0:45-1:15)
- Open terminal
- Run: `python inference.py` (with trained model)
- Let it run for 20 seconds (show smooth, efficient movements)
- Show training plot again in background window
- Ctrl+C to stop

### Segment 4: Show Code/Documentation (1:15-1:45)
- Open `README.md` in browser or editor
- Show "Quick Results" table
- Show "Multi-Agent Coordination" section
- Highlight links to blog and GitHub

### Segment 5: Links & Close (1:45-2:00)
- Show GitHub URL on screen
- Show HuggingFace Spaces URL on screen
- Show Project title slide

---

## Recording Checklist

### Before Recording
- [ ] Close all unnecessary applications
- [ ] Disable notifications (Plane mode or "Do Not Disturb")
- [ ] Set terminal/IDE to larger font (readable on video)
- [ ] Clear desktop (only show what you need)
- [ ] Test audio (if adding voiceover)
- [ ] Have script visible nearby

### During Recording
- [ ] Speak clearly and at good pace (~120 words/min)
- [ ] Move mouse deliberately (not too fast)
- [ ] Pause at key visuals (let them sink in)
- [ ] Leave plots/data visible for 5+ seconds
- [ ] Avoid long pauses or dead space

### After Recording
- [ ] Review footage (watch it back)
- [ ] Re-record if needed (can redo segments)
- [ ] Save as MP4, 1080p minimum
- [ ] File size should be < 100MB for upload

---

## Video Editing (Optional but Recommended)

### Simple Edits in DaVinci Resolve (FREE)
**Download:** https://www.davinciresolve.com/

**Simple tasks:**
1. Import video: File → Import Media
2. Add title card (0:00-0:05)
   - Right-click timeline → Add Title
   - Type: "Adaptive Warehouse OpenEnv"
3. Add text overlays at key moments
   - Text tool → +75% improvement
4. Speed up boring parts (2x speed)
5. Mute audio if background noise
6. Export: File → Export → YouTube

### Minimal Editing (5 minutes)
- Just add title card (0:00-0:05)
- Leave rest as-is
- Export as MP4

---

## Upload to YouTube

### Steps:
1. Go to https://youtube.com
2. Click profile → **"Create a post"** → **"Upload video"**
3. Select your MP4 file
4. Fill in details:
   - **Title:** "Adaptive Warehouse OpenEnv — DQN Agent Training"
   - **Description:**
     ```
     Meta PyTorch OpenEnv Hackathon 2026 Grand Finale
     
     This video demonstrates a warehouse logistics environment 
     with natural language instruction parsing, curriculum learning, 
     and multi-agent coordination.
     
     GitHub: https://github.com/XPOGBOY/meta-hackathon-2026
     HuggingFace Spaces: https://huggingface.co/spaces/XPOGBOY/warehouse-env
     Blog: [add blog link]
     
     Follow for more AI/RL projects!
     ```
   - **Thumbnail:** Auto-select or upload custom
   - **Visibility:** **UNLISTED** (not public, but judges can access)
   - **Age restriction:** No
5. Click **"Publish"**

### Get the URL:
- On your video, click **Share**
- Copy link: `https://youtu.be/YOUR_VIDEO_ID`

---

## Add URL to Submission

Update `SUBMISSION_URLS.txt`:

```
YouTube Video:
  https://youtu.be/YOUR_VIDEO_ID
  Duration: 90 seconds
  Format: MP4, 1080p
  Status: Unlisted
```

---

## Quality Checklist

- [ ] Video is 60-120 seconds long (not >2 min)
- [ ] Audio is clear (no background noise)
- [ ] Text is readable (large font)
- [ ] Movement is smooth (not too fast)
- [ ] Pacing is good (no long pauses)
- [ ] Key visuals are visible for 5+ seconds
- [ ] Links are clearly shown
- [ ] Video ends on strong note
- [ ] File is MP4, 1080p minimum
- [ ] YouTube link works and is unlisted

---

## Timing Breakdown

| Task | Time | Tools |
|------|------|-------|
| Record (with 1-2 retakes) | 15 min | OBS/ShareX |
| Edit (title + overlays) | 15 min | DaVinci Resolve |
| Upload to YouTube | 5 min | youtube.com |
| Add to submission | 2 min | Text editor |
| **TOTAL** | **~40 minutes** | |

---

## Pro Tips

1. **Use natural language:** Speak like you're explaining to a colleague, not reading a script
2. **Point at things:** Use cursor to highlight key elements
3. **Close other apps:** Reduces clutter and file size
4. **Test audio first:** Record a quick 1-min test, listen back
5. **Re-record segments:** You don't need to record all at once; do it in chunks
6. **Add pauses:** After showing a plot, pause 3 seconds so viewers absorb it
7. **End on a link:** Last thing judges see = your GitHub URL

---

## Example Video Timeline

```
0:00 — Title card + hook
0:15 — Show problem (demo failing agent)
0:30 — Results table + plots
0:45 — Trained agent performing well
1:00 — Multi-robot coordination clip
1:15 — Code/documentation
1:30 — Call-to-action + links
1:45 — Final slide with URLs
2:00 — End
```

---

## YouTube Best Practices

- Unlisted means judges can view but it won't show in search
- Keep thumbnail simple (high contrast, readable text)
- Description with links improves engagement
- Captions optional but recommended (use YouTube auto-caption)
- 16:9 aspect ratio (standard widescreen)

---

**Estimated Total Time:** 45 minutes (record + edit + upload)

**Deadline:** April 25, 2026

**Next Step:** Begin recording! 🎬
