# Bird Feeder Cameras: Compatibility Guide

> **Disclaimer:** This guide is based on a quick web survey of available products as of February 2026. Information is provided for educational purposes only. No endorsement of any specific product or brand is implied. Most products listed have not been tested with birdbird. Hardware specifications and availability may change. Always verify compatibility and features before purchasing.

This guide helps you choose camera hardware compatible with birdbird's batch video processing workflow.

## What birdbird Needs From a Camera

birdbird is designed for **offline batch processing** of motion-triggered video clips. The ideal camera:

- ✅ **Saves video files locally** (SD card or local storage)
- ✅ **Standard video formats** (AVI, MP4, MOV - anything ffmpeg can read)
- ✅ **Motion-triggered recording** (captures clips when birds visit)
- ✅ **Accessible files** (can copy clips to computer for processing)

What birdbird does **NOT** need:
- ❌ Real-time species identification
- ❌ Cloud storage or smartphone apps
- ❌ Live streaming or notifications
- ❌ Built-in AI features

## Camera Compatibility Matrix

### ✅ Fully Compatible (Recommended)

**Local storage cameras** - Best for birdbird workflow:

| Camera Type | Storage | Price Range | Notes |
|-------------|---------|-------------|-------|
| **Wilde & Oakes Camera Bird Feeder** | SD card | £30 | Budget option from B&M stores (UK), produces MJPEG AVI files |
| **Birdsnap PAV-Bird Feeder** | 64GB SD card (included) | ~$100 | Stores 40,000+ 10-second clips |
| **Green Backyard IP cameras** | 64GB SD card (included) | $100-200 | Various models with local storage |
| **Camojojo HiBird** | SD card | ~$150 | Saves MP4 (H.265), 4K-720p quality options |
| **Traditional trail cameras** | SD card | $50-300 | Motion-activated, reliable local storage |

**Key advantage:** Direct file access - just remove SD card and copy clips to computer.

### ⚠️ Partially Compatible (Not Recommended)

**Cloud storage with individual downloads** - Technically possible but impractical:

| Camera | Download Method | Why It's Tedious |
|--------|-----------------|------------------|
| **Bird Buddy** | One-by-one via app | Must manually download hundreds of clips individually |
| **Birdfy** (models without SD) | Via app (if available) | Download capability varies by model |

**Problem:** birdbird processes batches of 100-500 clips. Manually downloading each one takes hours.

**Verdict:** Only consider if you already own one and don't mind the tedious download workflow.

### ❌ Incompatible (Avoid)

**Cloud-only / proprietary streaming** - Cannot be used with birdbird:

- Cameras that only stream to apps (no download function)
- Proprietary formats that can't be exported
- Cameras with video retention < 7 days (clips expire before you can download)

## Commercial Smart Bird Feeders (For Reference)

These are popular products but **not designed for birdbird's use case**:

### All-in-One Smart Feeders

**Bird Buddy** ([mybirdbuddy.com](https://mybirdbuddy.com/))
- **Price:** $200-400 + optional subscriptions
- **Features:** 2K camera, real-time AI species ID, mobile app
- **Storage:** Cloud only (can download individual clips)
- **birdbird compatibility:** ⚠️ Possible but very tedious

**Birdfy** ([birdfy.com](https://www.birdfy.com/))
- **Price:** $100-270 + optional subscriptions
- **Features:** 1080p-6K cameras, AI identifies 6,000+ species, mobile app
- **Models:** Feeder 2 Pro, Feeder Vista (360° dual-camera), Hum Bloom (hummingbirds)
- **Storage:** Cloud primary, some models support SD card
- **birdbird compatibility:** ⚠️ Varies by model - check SD card support
- **2026 Innovation:** OrniSense LLM-powered AI with natural language interaction

**Other Brands:**
- **Bilantan** - 6,000+ species, night vision
- **PeckCam** - 10,000+ species identification
- **AviaryVue** - 6,000+ species with educational features
- **Camojojo** - 4K quality, local storage option

### Key Features (Commercial Products)

- Real-time AI species identification (6,000-11,000+ species)
- 1080p to 6K video quality
- Mobile apps with instant notifications
- Cloud storage (some with SD card backup)
- Solar power options
- Photo collections and sharing

### Why They're Not Ideal for birdbird

| Commercial Smart Feeders | birdbird Workflow |
|-------------------------|-------------------|
| Real-time classification | Batch processing after the fact |
| Cloud infrastructure | Offline processing |
| $200-400 hardware cost | Works with budget cameras (£30+) |
| Monthly subscriptions | One-time setup |
| Individual photo collections | Automated highlight reels from videos |
| Designed for casual users | Designed for power users and researchers |

**Bottom line:** Smart feeders are great for real-time bird watching and instant notifications, but birdbird offers more powerful video analysis and highlight generation for users who prefer batch processing.

## Open-Source Alternatives

These projects build DIY bird feeder cameras, but focus on **real-time capture** rather than **batch video processing**:

### Hardware-Focused Projects

**[Birdiary Station](https://github.com/Birdiary/station)** - Full DIY smart feeder
- Smart bird feeder with environmental sensor, microphone, balance, camera
- AI species identification, publishes data to birdiary.de
- Complete hardware build guide
- **Similar to commercial products, but open-source**

**[Birbcam](https://github.com/jdpdev/birbcam)** - Raspberry Pi camera
- Motion-triggered capture for bird feeders
- v2.0 added "BIRBVISION" species identification
- Raspberry Pi focused

**[countYourBirds](https://github.com/jsten07/countYourBirds)** - Automated counter
- TensorFlow Lite detection + species classification
- Counts and saves images, publishes to opensensemap.org
- Raspberry Pi implementation

**[BirdCam (ccrenfroe)](https://github.com/ccrenfroe/BirdCam)** - Detector and classifier
- Raspberry Pi + TensorFlow Lite
- Real-time detection and classification

### Integration Projects

**[WhosAtMyFeeder](https://github.com/mmcc-xx/WhosAtMyFeeder)** - Frigate NVR integration
- Listens for MQTT snapshots from Frigate
- Runs species classifier on images
- Flask web UI for viewing visitors
- **Closest to birdbird's philosophy** (processes existing data)

**[BirdCam (johnstaveley)](https://github.com/johnstaveley/BirdCam)** - Home Assistant + Azure
- USB webcam with Home Assistant motion trigger
- Azure Function for filtering false positives
- Cloud-based classification

### Photography Tools

**[Bird-Watcher (platdrag)](https://github.com/platdrag/Bird-Watcher)** - DSLR trigger
- OpenCV motion detection on Raspberry Pi
- Triggers connected DSLR via libgphoto2
- For high-quality bird photography

### How birdbird is Different

| Other Open-Source Projects | birdbird |
|---------------------------|----------|
| Real-time capture & classify | **Batch processing existing footage** |
| Raspberry Pi + camera builds | **Works with any camera** |
| Live camera stream / single images | **Hundreds of pre-recorded video clips** |
| Individual classified images | **Automated highlight reels + JSON data** |
| No audio analysis | **BirdNET song detection with audio clips** |
| Minimal video processing | **Segment extraction, concatenation, ffmpeg pipeline** |

**Complementary approach:** You could use a Raspberry Pi project to *capture* clips, then use birdbird to *analyze and create highlights* from the footage.

## Recommendations by Use Case

### Budget Bird Watcher (£30-100)

**Best choice:** Simple local-storage camera
- **Wilde & Oakes Camera Bird Feeder** (£30 at B&M, UK)
- **Generic trail camera** (£40-80) mounted near feeder
- Add your own SD card (64-128GB recommended)

**Why:** No ongoing costs, perfect for birdbird's batch processing, proven to work.

### Serious Birder (£100-300)

**Best choice:** Higher-quality local-storage camera
- **Birdsnap PAV-Bird Feeder** - Optimized for 10-second clips
- **Camojojo HiBird** - 4K quality, MP4 format
- **Green Backyard cameras** - Good build quality, includes SD card

**Why:** Better video quality for species identification, larger included storage, more durable hardware.

### DIY Enthusiast (Variable cost)

**Best choice:** Build your own with Raspberry Pi
- Use open-source projects like Birdiary Station or Birbcam for capture
- Process resulting footage with birdbird for highlights
- Full control over hardware and software

**Why:** Learning experience, complete customization, can upgrade components over time.

### Already Own Smart Feeder (No additional cost)

**If you have Bird Buddy or similar:**
1. Check if you can download videos (not just view in app)
2. Test downloading a small batch (10-20 clips)
3. If download works, consider whether manual downloading is worth it
4. Otherwise, use the smart feeder for real-time ID and add a cheap SD card camera for birdbird

## Key Specifications to Check

When shopping for a birdbird-compatible camera, verify:

### Essential
- ✅ **Local storage option** (SD card slot)
- ✅ **Video file export** (not just streaming)
- ✅ **Standard formats** (MP4, AVI, MOV, MKV)
- ✅ **Motion-triggered recording** (not just continuous)

### Nice to Have
- 1080p or higher resolution (better for species identification)
- 30fps frame rate (smooth video)
- Night vision (captures evening visitors)
- Weatherproof housing (durability)
- Solar power (convenient placement)

### Not Important for birdbird
- Real-time AI identification (birdbird does this offline)
- Cloud storage (unless downloadable)
- Mobile app (not needed for batch processing)
- Live streaming (not used)

## Technical Details: Compatible Formats

birdbird uses ffmpeg for video processing and supports any format ffmpeg can read, including:

- **AVI** (MJPEG, H.264) - Common in budget cameras
- **MP4** (H.264, H.265/HEVC) - Most common modern format
- **MOV** (QuickTime) - Apple devices
- **MKV** (Matroska) - Open format
- **WebM** - Web-optimized format

**The Wilde & Oakes camera produces:** MJPEG AVI (1440x1080, 30fps, ~10-second clips, ~27MB each) - works perfectly with birdbird.

## FAQs

### Can I use a regular security camera?

Yes! Any motion-triggered camera that saves video files locally will work. Just mount it to view your bird feeder.

### Do I need a camera with AI features?

No. birdbird provides AI species identification (BioCLIP visual + BirdNET audio) during batch processing. Built-in AI just adds cost.

### What SD card size do I need?

- **32GB** - Stores ~1,200 clips (10s each at 27MB)
- **64GB** - Stores ~2,400 clips
- **128GB** - Stores ~4,800 clips

For daily/weekly processing, 64GB is plenty.

### Can I use a webcam connected to a computer?

Technically yes, but you'd need software to handle motion detection and save clips. A standalone camera is much simpler.

### What about 4K cameras?

Higher resolution helps with species identification, but increases file sizes and processing time. 1080p is a good balance.

## Summary

**For birdbird's batch video processing workflow:**

1. ✅ **Best option:** Budget local-storage camera (Wilde & Oakes £30, trail cameras £40-80)
2. ⚠️ **Acceptable:** Premium local-storage cameras if you want higher quality
3. ❌ **Avoid:** Cloud-only smart feeders unless they offer easy batch downloads

**The key insight:** birdbird's value is in *processing* video, not *capturing* it. A simple £30 camera produces exactly the same input as a £300 smart feeder, but without the subscription fees or cloud dependency.

---

**Related:**
- [README.md](README.md) - Main project documentation
- [CLAUDE.md](CLAUDE.md) - Development guidance
- [Commercial product links](#commercial-smart-bird-feeders-for-reference) - For comparison purposes
