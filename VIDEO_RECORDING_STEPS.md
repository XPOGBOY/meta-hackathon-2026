# 🎬 Video Recording Guide — Step-by-Step

**Target:** 2-3 minute demo video | **Format:** MP4 | **Quality:** 1080p (minimum)

---

## Quick Start (5-minute setup)

### Step 1: Choose Recording Software

**Option A: OBS Studio (FREE, Recommended)** ⭐
- Download: https://obsproject.com/
- Setup time: 5 min
- Output: Professional MP4 (no watermark)

**Option B: Windows Game Bar (Built-in, Easy)**
- Keyboard shortcut: **Windows Key + G**
- Setup time: 0 min (no download needed)
- Output: MP4 to Videos/Captures

**Option C: ScreenFlow (macOS only)**
- Cost: ~$30 or free trial
- Output: MP4/MOV

---

## Method 1: OBS Studio (Recommended)

### Setup (5 minutes)

1. **Install OBS:**
   - Download from https://obsproject.com/
   - Run installer, follow defaults
   - Launch OBS Studio

2. **Configure OBS for Screen Recording:**
   - Click **"+"** under **Sources** section
   - Select **"Display Capture"** (or "Window Capture")
   - Choose your screen/monitor
   - Enable **Audio Input Device** (for your microphone)

3. **Set Recording Settings:**
   - File menu → **Settings**
   - Navigate to **Output** tab
   - Set Recording Format: **mkv** or **mp4**
   - Encoding: **Software (libx264)**
   - Bitrate: **5000-8000 Kbps** (for 1080p)
   - Click **Apply → OK**

4. **Test Audio:**
   - Speak into microphone
   - Watch the audio meter in OBS (should show ~20-30 dB)
   - If no response, change audio input device

---

### Recording (10 minutes)

**Before you hit Record:**
- [ ] Mute/close Slack, Teams, notifications
- [ ] Open all demo windows (terminal, plots folder, browser)
- [ ] Have VIDEO_SCRIPT.md open for reference
- [ ] Test your microphone

**Recording Steps:**

1. Click **"Start Recording"** button in OBS (or Ctrl+Alt+R)
2. Wait 3 seconds for slate
3. Begin narration following VIDEO_SCRIPT.md

**Narration Breakdown (follow this flow):**

```
[0:00-0:20] Opening Hook
- Read opening hook from VIDEO_SCRIPT.md
- Keep energy high, speak clearly
- Pause at natural breaks

[0:20-0:50] Problem & Solution
- Show file explorer: warehouse_env/
- Show training results: docs/plots/
- Display key metrics

[0:50-1:30] Training Results
- Open: docs/plots/training_reward.png
- Hold for 5-10 seconds (point out key features)
- Show: results/TRAINING_SUMMARY.md
- Mention curriculum learning progression

[1:30-2:15] Multi-Robot Coordination
- Show environment running
- Screen-capture live inference if possible (or demo replay)
- Narrate coordination mechanics

[2:15-2:45] Conclusion & Links
- Show GitHub repo link
- Show HF Spaces URL
- End with confidence: "Thank you. Check the links below."

TOTAL: ~2:45
```

4. Stop recording when done (Ctrl+Alt+R or click **Stop Recording**)
5. OBS saves to Documents folder by default (check for `.mp4` or `.mkv`)

---

## Method 2: Windows Game Bar (Easiest, Built-in)

### Recording (Fastest)

1. **Start Recording:**
   - Press **Windows Key + G** (opens Game Bar)
   - Click **"Start Recording"** (or click record icon)
   - You'll see red dot in top-left corner

2. **Narrate while recording:**
   - Follow VIDEO_SCRIPT.md
   - Speak clearly into microphone
   - Navigate windows/folders as needed

3. **Stop Recording:**
   - Press **Windows Key + G** again
   - Click **Stop** or press **Windows Key + Alt + R**
   - Windows automatically saves to: `Videos\Captures\`

4. **Output:**
   - Look for `Recording [timestamp].mp4` in Videos\Captures
   - Typical size: 50-150 MB for 2-3 min video

---

## What to Show During Recording

### Scene 1: Opening/Problem (20 seconds)
```
Visual:
- Desktop or project folder
- Maybe animate moving robot on warehouse grid
- Show: "Adaptive Warehouse OpenEnv" title slide

Actions:
- Click on docs/ folder
- Show warehouse_env/ folder structure
```

### Scene 2: Training Results (30 seconds)
```
Visual:
- Navigate to docs/plots/
- Open training_reward.png (show plot clearly)
- Keep on screen for 5-10 seconds
- Then open results/TRAINING_SUMMARY.md

Actions:
- Take time zooming to plots folder
- Click to open image
- Point at key parts (where reward jumps)
```

### Scene 3: Multi-Robot Demo (45 seconds)
```
Visual:
- Try to run live demo if possible
  If not, show recorded/sample output
- Show environment grid
- Show 2 robots moving
- Show task queue

Optional: Run inference live
$ python inference.py
(let it run for 20-30 seconds)
```

### Scene 4: Conclusion (15 seconds)
```
Visual:
- Show GitHub link on screen
- Show HF Spaces URL
- Show blog post link
- End slide: "Hackathon 2026"

Actions:
- Type in browser or show screenshot
```

---

## Post-Processing (5-10 minutes)

### If using OBS or Game Bar:
Video should already be in MP4 format. **No heavy editing needed.**

### Optional Enhancements:
- **Add intro slide:** Use simple video editor (e.g., ClipChamp) to prepend title slide
- **Add outro slide:** Final 5 seconds with links/credits
- **Trim silence:** Remove any dead air at start/end
- **Normalize audio:** Ensure volume is consistent

### Video Editors (Free Options):
1. **ClipChamp** (web-based, easiest): https://clipchamp.com/
2. **HandBrake** (for compression): https://handbrake.fr/
3. **DaVinci Resolve** (professional, free): https://www.blackmagicdesign.com/products/davinci

---

## Export & Save

### MP4 Export Settings:
- **Codec:** H.264 (or H.265 for better compression)
- **Resolution:** 1080p (1920x1080)
- **Frame Rate:** 30fps (or match your recording capture rate)
- **Bitrate:** 5-10 Mbps (HD quality)
- **File size:** Typically 50-200 MB for 2-3 min video

### Save Location:
```
docs/video/DEMO_VIDEO_FINAL.mp4
```

### Backup/Alternative Locations:
- Google Drive (for easy sharing)
- YouTube (unlisted, for embedded submission)
- GitHub Releases (if repo allows large files)

---

## Pre-Submission Checklist

- [ ] Video is 2-3 minutes long
- [ ] Audio is clear (no background noise)
- [ ] Narration follows VIDEO_SCRIPT.md
- [ ] All key sections visible (problem → solution → results → demo → links)
- [ ] MP4 format (not MOV, AVI, or WebM)
- [ ] Resolution is 1080p or higher
- [ ] File size reasonable (<300 MB)
- [ ] Video plays without errors in local video player
- [ ] Links are visible and legible
- [ ] Ready for public submission

---

## Submission Integration

After recording:

1. **Save video to:** `docs/video/DEMO_VIDEO_FINAL.mp4`
2. **Commit to git:**
   ```bash
   git add docs/video/DEMO_VIDEO_FINAL.mp4
   git commit -m "Add demo video for submission"
   ```
3. **Upload to YouTube (if needed):**
   - Upload as **Unlisted** (private link only)
   - Get shareable link
   - Include in submission docs
4. **Update SUBMISSION_CHECKLIST.md:**
   - Add video link
   - Confirm all deliverables ready

---

## Troubleshooting

### Audio Issues
- **No sound:** Check microphone input device in OBS settings
- **Loud background:** Wear headphones to prevent echo
- **Quiet voice:** Check system volume (~70%) and speak closer to mic

### Video Quality Issues
- **Blurry/pixelated:** Increase bitrate to 8000+ Kbps or record at 1080p 60fps
- **Stuttering:** Close other apps (browsers, IDEs, etc.)
- **Dropped frames:** OBS shows "Skipped Frames" — reduce screen resolution or bitrate

### File Issues
- **Won't save:** Check disk space (need ~500 MB free)
- **Corrupted file:** Re-record (video editing issue usually means recapture)
- **Wrong format:** Re-export from video editor with MP4 codec

---

## Pro Tips

✅ **Do:**
- Record in quiet environment
- Speak clearly and confidently
- Maintain consistent pace (not too fast)
- Let plots/results stay on screen 5+ seconds
- Use clear mic (USB headset is ~$15-30)
- Test audio before full record

❌ **Don't:**
- Ramble or go off-script
- Show private API keys/credentials (blur if needed)
- Rush through metric displays
- Forget to show links at end
- Record with shaky mouse movements

---

## Timeline Summary

- Setup recording software: **5 min**
- Prepare demo windows: **5 min**
- Record video (1-2 takes): **10-15 min**
- Post-processing/editing: **5-10 min**
- Test & finalize: **5 min**

**Total time: 30-45 min**

---

## Ready? 🎬

1. Install OBS or use Windows Game Bar
2. Gather reference materials (VIDEO_SCRIPT.md, plots)
3. Set your microphone level
4. Hit Record
5. Follow the script
6. Save as MP4
7. Update submission docs
8. You're done! 🎉
