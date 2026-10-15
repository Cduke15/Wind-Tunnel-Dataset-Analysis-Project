# Wind-Tunnel-Dataset-Analysis-Project

**Our 2026 senior project repository: Colby Duke and Jocelyn Ruiz, University of Tennessee Martin.**

Hello! We've designed a program that can read cih and mraw data files because we lacked a tool to do so - we use two main Python libraries: pyMRAW and OpenCV.

pyMRAW reads the raw data (frame by frame) and OpenCV turns it into a viewable video.

Links to them are here: 
https://pypi.org/project/pyMRAW/
https://opencv.org/

----------------------------------------------------------------------------------------------------------------------

Alongside this, we added encryption and authentication using several methods:

AES-128 with CTR and 16 byte Initialization Vector (IV).

PBKDF2 (Password-Based Key Derivation Function 2) using SHA-256 with 100,000 iterations. 

Salt which generates a random 16-byte hex inside the header file.

HMAC-SHA256 for verification of the password you will choose for the file, at which it verifies or else it denies access.

Do note that we used several hazmat layers as Fernet was giving us trouble so please be careful with these - they can be dangerous if used incorrectly!

Links to the library is here:
https://cryptography.io/en/latest/

----------------------------------------------------------------------------------------------------------------------

~~~

**INSTRUCTIONS for our MRAW data reader program to run**

You MUST have Python installed via the latest Python installer, not just through your IDE.
You can get the latest Python extension here: https://www.python.org/downloads/

You MUST also have the libraries listed below:
    pyMRAW
    openCV-python
    cryptography
    numpy (analysis code uses it directly, but it is automatically installed wih pyMRAW and OpenCV) 

If you need them, run this command in a fresh terminal: python -m pip install pyMRAW opencv-python cryptography numpy
If you only need one, simply run: pip install (library)

Once you have all three libraries above, select a folder within your IDE to open from, placing both the cih and mraw files within. Depending on your IDE interface, you may be able to simply put them within your project folder so long as it can view it.

You then place the source files, video_player.py and main.py, inside your project folder.

Within the main.py, change the header file to one of cih files' names, not the MRAW files. NOTE: you must have the MRAW file of the same exact name of the cih for it to read it!

Once that is done, simply run the main.py and the program will start. It will ask you for a password for the file. Enter one you can remember!

It will then go through and encrypt the data file, making a secure copy in case of data loss. This allows you to retain your original copy and delete it if you wish.

After this, re-run the program and enter the password you put in to view the playback. If it is correct, it will:
1. Analyze every frame of the video for particle-shock interactions
2. Save the results to the particle_shock_events folder.
3. Open the playback window, demonstrating the analysis while it plays.

A video pop-up should then show up titled 'MRAW Playvideo' at which you can then press:
- 'Space' to pause/resume
- 'q' to quit when you are done viewing the data.
- 's' to slow down
- 'f' to speed up
- 'r' to rewind by 100 frames 

~~~
----------------------------------------------------------------------------------------------------------------------

## Particle-shock Event Detection

The goal is to find the interactions that appear on the immediate left face of the black block in the wind tunnel, count them, and show where each one is most visible. All of this is in video_player.py.

### How it works:
1. Strip - Only a narrow strip along the left side of the black block is examined (the red rectangle on screen). Everything else in the frame is ignored.
2. Background - The program keeps a slowly updating picture of what the strip looks like when nothing is happening (the wall's speckle structure).
3. Compare - Each fram is blurred slightly and compared with that background. Overall brightness flicker is removed first.
4. Treshold - A pixel counts as changed if it differes from the background by more than 5x the camera's own noise level. The noise level is measured from the video itself at the start of each analysis, so there is no fixed number to guess.
5. Regions - Changed pixels are grouped into connected regions. Regions smaller than 10 pixels are ignored  so single flickering pixels don't count.
6. Events - Frames that contain at least one region are "active". Active frames within 10 frames of each other are merged into one event. Groups with fewer than 3 active frames are discarded as noise.

### What the terms mean
- Area: The percentage of the strip's pixels covered by detected regions in a frame. The strip is about 2,600 pixels, so 1% is roughly 26 pixels. It measures image pixels, not physical size. A larger or higher-contrast disturbance gives a larger area.
- Event: One interaction from start to finish: a run of active frames, including short gaps of up to 10 frames.
- Peak: The frame inside an event with the largest area, meaning where the interaction is most visible. If two frames tie, the earlier one is used.
- Regions: The number of separate detected areas in a frame. Two regions means two separate disturbances at the same time.

### What you see on screen
- Red rectangle: the detection strip, with no event at the current frame.
- Green rectangle (thicker): the current frame is inside a detected event. The analysis runs before playback and stores each event's start and end frame, so this is a replay of stored results, not a new detection. Short gaps inside an event stay green.
- Yellow rectangle: the peak frame of the current event. The label also shows PEAK.
- Light-blue boxes: each detected region on the current frame.
- Frame: the current frame out of the total, for example Frame: 8,237 / 72,261.
- Interaction / regions: the area percentage and region count for the current frame.
- Event: 17 / 43: how many events have started so far out of the total found. It counts back down if you rewind.
- IN EVENT n (start-end): the event you are inside and its frame range.

### What gets saved
Everything is written to the particle_shock_events folder:
- Peak images (event_###_frames_a-b_peak_c.png): the peak frame of each event, enlarged 4x, with the strip in red and a yellow box around each detected region. The caption shows the event number, frame range, peak frame, area and region count.
- Particle_shock_events.csv: one row per event with start frame, end frame, peak frame, peak area and peak region count. Events here are ranked by peak area, highest first.
- Particle_shock_playback_report.csv: written when playback ends. It lists each event in time order, its rank from the events file, and whether playback reached it (Yes/No). This lets you compare the playback tally against the analysis results.

Note: playback numbers events in time order so the live counter counts up 1, 2, 3... The events CSV ranks them by area. The "Analysis Rank" column in the playback report links the two.
All frame numbers shown to you are 1-based (the first frame is frame 1).

### Settings
Everything you can tune is at the top of video_player.py:
- ROI_X, ROI_Y, ROI_WIDTH, ROI_HEIGHT (default: 214, 20, 20, 130) Position and size of the detection strip. Adjust if the red rectangle doesn't sit along the black block.
- DIFF_SIGMAS (default: 5.0) How far a pixel must differ from the background, in multiples of camera noise. Lower catches fainter interactions but gives more false hits.
- MIN_REGION_AREA (default: 10) Smallest region, in pixels, that counts.
- EVENT_GAP (default: 10) Active frames closer together than this merge into one event. Lower it if separate interactions are being merged.
- MIN_EVENT_FRAMES (default: 3) Events with fewer active frames are discarded.
- BACKGROUND_RATE (default: 0.005) How fast the background follows the video. Smaller values have a longer memory.
- MAX_EVENTS (default: None) Keep only the top N events by area. None keeps all, which keeps the live counter accurate.
- KNOWN_INTERACTION_FRAMES (default: a list of frame numbers) Frame numbers where you have seen an interaction, used for the check below.

### Checking and tuning against your own data
Put frame numbers where you have visually confirmed an interaction into KNOWN_INTERACTION_FRAMES (use the frame number shown in the playback window). After analysis the program prints whether each one was detected, for example:
    
    Frame  2,290: DETECTED area  4.23% (frame 2,288)  [inside an event]
    Frame  2,477: MISSED   area  0.00% (frame 2,477)  [not in an event]
    
If some are missed, lower DIFF_SIGMAS or MIN_REGION_AREA. If there are too many false events, raise them.

### Required change in main.py
Playback needs the events from the analysis. In main.py, the playback call must pass them in:

    events = video_player.analyze_video(video_stream)
    video_player.save_interaction_events(video_stream, events)
    video_player.play_video(video_stream, events)

### Limitations
- It detects change, not particles. Anything that alters the strip (debris, camera shake, a lighting change) can count as an interaction. The size filter and threshold reduce this but cannot tell what caused a change.
- Overlapping interactions merge into one event. The region count shows when more than one was present.
- Long-lasting changes fade. A change that never goes away is slowly absorbed into the background and stops being detected.
- Thresholds depend on the video. The defaults were set from sample frames and should be checked with the known-frames printout for each new dataset.
- Analysis time. Every frame is decrypted and analyzed before playback, so a large file takes a while to start.


Overall this program is designed to read, encrypt, authenticate, run, and analyze cih and mraw files!
