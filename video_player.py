import cv2
import os
import csv
import numpy as np
from bisect import bisect_right


# ============================================================
# SETTINGS
# ============================================================

# Your actual MRAW frame is 256 x 192
FRAME_WIDTH = 256
FRAME_HEIGHT = 192

# ------------------------------------------------------------
# REGION OF INTEREST (ROI)
#
# The tall, narrow strip along the LEFT face of the black block
# where the particle-shock interactions appear.
#
# Estimated from your screenshots. The bottom stops above the
# bright floor edge so its glare can't trigger false events.
# ------------------------------------------------------------

ROI_X = 214
ROI_WIDTH = 20          # reaches x = 234, the black block's edge
ROI_Y = 20
ROI_HEIGHT = 130        # reaches y = 150, above the bright floor edge

# ------------------------------------------------------------
# INTERACTION DETECTOR
#
# Every frame is compared to a slowly updating "background" of
# the strip (the quiet wall texture). Anything that differs from
# that background by a clear margin and forms a connected region
# of at least MIN_REGION_AREA pixels counts as an interaction.
# ------------------------------------------------------------

# How far a pixel must differ from the background, measured in
# multiples of the camera's own noise level (measured from your
# video at the start of the analysis).
#   Lower  = more sensitive (catches fainter interactions,
#            but more false hits)
#   Higher = stricter
DIFF_SIGMAS = 5.0

# Smallest region (in pixels) that counts. Single flickering
# pixels are ignored. Lower = catches smaller interactions.
MIN_REGION_AREA = 10

# How fast the background follows the video (0-1). Small values
# keep a long memory, so a slow interaction isn't absorbed.
BACKGROUND_RATE = 0.005

# While an interaction region is present, the background under it updates this
# many times slower, so interactions don't "burn in".
BACKGROUND_FREEZE_FACTOR = 0.1

# Ignore the first few frames while the background settles.
WARMUP_FRAMES = 10

# Number of frame pairs sampled to measure camera noise.
NOISE_SAMPLE_PAIRS = 60

# Analyze EVERY frame.
ANALYSIS_STEP = 1

# How close two active frames can be and still belong to the
# same interaction event.
EVENT_GAP = 10

# Ignore events shorter than this many active frames.
MIN_EVENT_FRAMES = 3

# Maximum number of events to keep (highest activity first).
# None = keep all, which keeps the live counter accurate.
MAX_EVENTS = None

# ------------------------------------------------------------
# CALIBRATION
#
# Frame numbers (as shown in the playback window) where YOU saw
# an interaction. After analysis the program reports whether
# each one was detected, so you can tune the settings above.
# ------------------------------------------------------------

KNOWN_INTERACTION_FRAMES = [552, 801, 807, 2230, 2290, 2477, 2551]

# A known frame counts as detected if an active frame is within
# this many frames of it.
KNOWN_FRAME_TOLERANCE = 3

# Folder for saved results.
OUTPUT_FOLDER = "particle_shock_events"

# Saved event pictures are enlarged by this factor.
SAVE_UPSCALE = 4

# Colors (BGR)
COLOR_ROI_IDLE = (0, 0, 255)      # red    - no event
COLOR_ROI_EVENT = (0, 255, 0)     # green  - inside a detected event
COLOR_ROI_PEAK = (0, 255, 255)    # yellow - the peak frame of an event
COLOR_REGION = (255, 200, 0)        # blue-ish - detected interaction
COLOR_TEXT = (255, 255, 255)

# Filled in by analyze_video():
#   FRAME_SCORES: frame index -> % of the ROI covered by interactions
#   FRAME_BOXES:  frame index -> list of (x, y, w, h) interaction boxes
#                 in full-frame coordinates (only frames that have any)
FRAME_SCORES = {}
FRAME_BOXES = {}


# ============================================================
# GET TOTAL NUMBER OF FRAMES
# ============================================================

def get_total_frames(images):
    # Encrypted MRAW stream
    if hasattr(images, "total_frames"):
        return images.total_frames
    # Normal NumPy array
    return images.shape[0]


# ============================================================
# GET ROI
# ============================================================

def get_roi(frame):
    return frame[ROI_Y:ROI_Y + ROI_HEIGHT, ROI_X:ROI_X + ROI_WIDTH]


def get_smoothed_roi(frame):
    roi = get_roi(frame).astype(np.float32)
    return cv2.GaussianBlur(roi, (3, 3), 0)


# ============================================================
# MEASURE CAMERA NOISE
# ============================================================

def estimate_noise(images, total_frames):
    """
    Measure how much the strip changes between neighboring frames
    when nothing is happening. Uses the median, so the (rare)
    interactions don't inflate the estimate.
    """

    count = min(NOISE_SAMPLE_PAIRS, total_frames - 1)
    positions = np.linspace(0, total_frames - 2, count).astype(int)

    deviations = []

    for i in positions:
        a = get_smoothed_roi(images[int(i)])
        b = get_smoothed_roi(images[int(i) + 1])

        d = b - a
        d = d - np.median(d)
        deviations.append(np.abs(d).ravel())

    deviations = np.concatenate(deviations)

    # 1.4826 turns a median absolute deviation into a standard
    # deviation; sqrt(2) removes the doubling from differencing.
    sigma = float(np.median(deviations) * 1.4826 / np.sqrt(2))

    return max(sigma, 0.1)


# ============================================================
# STRIP DETECTOR
# ============================================================

class StripDetector:

    def __init__(self, threshold):
        self.threshold = threshold
        self.background = None
        self.count = 0
        self.open_kernel = np.ones((2, 2), np.uint8)
        self.grow_kernel = np.ones((5, 5), np.uint8)

    def process(self, frame):
        """
        Returns (score, boxes).
        score = % of the ROI covered by interaction regions
        boxes = list of (x, y, w, h) in full-frame coordinates
        """

        roi = get_smoothed_roi(frame)

        if self.background is None:
            self.background = roi.copy()
            self.count = 1
            return 0.0, []

        # Difference from the quiet wall texture. Subtracting the
        # median removes overall brightness flicker.
        delta = roi - self.background
        delta = delta - np.median(delta)

        mask = (np.abs(delta) >= self.threshold).astype(np.uint8)

        # Remove isolated speckles
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.open_kernel)

        # Group into connected regions
        n, _, stats, _ = cv2.connectedComponentsWithStats(
            mask, connectivity=8
        )

        boxes = []
        area_total = 0

        for i in range(1, n):
            x, y, w, h, area = stats[i]

            if area >= MIN_REGION_AREA:
                boxes.append((ROI_X + int(x), ROI_Y + int(y),
                              int(w), int(h)))
                area_total += int(area)

        # Update the background. Faster at first (a running mean),
        # then settles to BACKGROUND_RATE. Pixels under a region
        # update much more slowly.
        rate = max(BACKGROUND_RATE, 1.0 / (self.count + 1))
        self.count += 1

        rates = np.full(roi.shape, rate, dtype=np.float32)

        if boxes:
            near_region = cv2.dilate(mask, self.grow_kernel)
            rates[near_region > 0] = rate * BACKGROUND_FREEZE_FACTOR

        self.background += rates * (roi - self.background)

        total_pixels = roi.shape[0] * roi.shape[1]
        score = (area_total / total_pixels) * 100

        return score, boxes


# ============================================================
# ANALYZE VIDEO FOR PARTICLE-SHOCK EVENTS
# ============================================================

def analyze_video(images):
    total_frames = get_total_frames(images)

    print("\n========================================")
    print("PARTICLE-SHOCK ACTIVITY ANALYSIS")
    print("========================================")
    print(f"Total frames: {total_frames}")
    print(f"Monitoring ROI: x={ROI_X}, y={ROI_Y}, "
          f"width={ROI_WIDTH}, height={ROI_HEIGHT}")

    print("\nMeasuring camera noise...")
    noise = estimate_noise(images, total_frames)
    threshold = max(DIFF_SIGMAS * noise, 1.0)
    print(f"Noise level: {noise:.2f}   "
          f"Detection threshold: {threshold:.2f} "
          f"({DIFF_SIGMAS} x noise)")

    print("\nAnalyzing EVERY frame.")
    print("This may take some time.")
    print("Please wait...\n")

    FRAME_SCORES.clear()
    FRAME_BOXES.clear()

    detector = StripDetector(threshold)

    for frame_idx in range(0, total_frames, ANALYSIS_STEP):
        score, boxes = detector.process(images[frame_idx])

        # Let the background settle before trusting detections
        if frame_idx < WARMUP_FRAMES:
            score, boxes = 0.0, []

        FRAME_SCORES[frame_idx] = score

        if boxes:
            FRAME_BOXES[frame_idx] = boxes

        if frame_idx % 1000 == 0 and frame_idx > 0:
            percentage = (frame_idx / total_frames) * 100
            print(f"Analyzed {frame_idx:,} / {total_frames:,} "
                  f"({percentage:.1f}%)")

    # ---------------- active frames ----------------
    active_frames = [
        (frame_idx, FRAME_SCORES[frame_idx])
        for frame_idx in sorted(FRAME_SCORES)
        if FRAME_SCORES[frame_idx] > 0
    ]

    print(f"\nFrames with an interaction: {len(active_frames)}")

    # ---------------- group into events ----------------
    events = []

    if len(active_frames) > 0:
        event_start = active_frames[0][0]
        event_end = active_frames[0][0]
        event_frames = [active_frames[0]]

        for frame_number, score in active_frames[1:]:
            if frame_number - event_end <= EVENT_GAP:
                event_end = frame_number
                event_frames.append((frame_number, score))
            else:
                if len(event_frames) >= MIN_EVENT_FRAMES:
                    events.append((event_start, event_end, event_frames))

                event_start = frame_number
                event_end = frame_number
                event_frames = [(frame_number, score)]

        # Final event
        if len(event_frames) >= MIN_EVENT_FRAMES:
            events.append((event_start, event_end, event_frames))

    # ---------------- peak frame per event ----------------
    # The peak is the frame where the interaction covers the most
    # area, i.e. where it is most visible.
    event_information = []

    for start, end, frames in events:
        peak_frame = max(frames, key=lambda x: x[1])
        event_information.append((start, end, peak_frame[0], peak_frame[1]))

    # Calibration uses ALL events, before any trimming
    print_calibration(event_information)

    # Sort by highest activity, optionally keep top events
    event_information.sort(key=lambda x: x[3], reverse=True)
    if MAX_EVENTS is not None:
        event_information = event_information[:MAX_EVENTS]

    # ---------------- display ----------------
    print("\n========================================")
    print("PARTICLE-SHOCK CANDIDATE EVENTS")
    print("========================================")

    if len(event_information) == 0:
        print("No candidate interaction events found.")
    else:
        print(f"Events found: {len(event_information)}\n")

        for rank, event in enumerate(event_information, start=1):
            start, end, peak_frame, peak_score = event
            print(f"Event {rank}: frames {start + 1}-{end + 1}, "
                  f"peak {peak_frame + 1}, "
                  f"area {peak_score:.2f}%")

    print("\n========================================")
    print("ANALYSIS COMPLETE")
    print("========================================")

    return event_information


# ============================================================
# CALIBRATION REPORT
# ============================================================

def print_calibration(event_information):
    if not KNOWN_INTERACTION_FRAMES:
        return

    print("\n========================================")
    print("CHECK AGAINST YOUR KNOWN INTERACTIONS")
    print("========================================")

    hits = 0

    for shown in KNOWN_INTERACTION_FRAMES:
        idx = shown - 1

        # Strongest score within the tolerance window
        best_score = 0.0
        best_frame = idx

        for j in range(idx - KNOWN_FRAME_TOLERANCE,
                       idx + KNOWN_FRAME_TOLERANCE + 1):
            s = FRAME_SCORES.get(j, 0.0)
            if s > best_score:
                best_score = s
                best_frame = j

        in_event = any(
            start <= idx <= end for start, end, _, _ in event_information
        )

        if best_score > 0:
            status = "DETECTED"
        else:
            status = "MISSED"

        if best_score > 0:
            hits += 1

        print(f"Frame {shown:>6,}: {status:<8} "
              f"area {best_score:5.2f}% "
              f"(frame {best_frame + 1:,})"
              f"{'  [inside an event]' if in_event else '  [not in an event]'}")

    print(f"\nDetected {hits} of {len(KNOWN_INTERACTION_FRAMES)} "
          f"known interactions.")

    if hits < len(KNOWN_INTERACTION_FRAMES):
        print("Missed some? Lower DIFF_SIGMAS or MIN_REGION_AREA.")


# ============================================================
# SAVE PARTICLE-SHOCK EVENTS
# ============================================================

def save_interaction_events(images, events):
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)

    print("\n========================================")
    print("SAVING PARTICLE-SHOCK EVENTS")
    print("========================================")

    csv_path = os.path.join(OUTPUT_FOLDER, "particle_shock_events.csv")

    with open(csv_path, "w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Event", "Start Frame", "End Frame",
                         "Peak Frame", "Peak Interaction Area (%)",
                         "Peak Region Count"])

        for rank, event in enumerate(events, start=1):
            start, end, peak_frame, peak_score = event

            frame = images[peak_frame]

            display_frame = cv2.normalize(frame, None, 0, 255,
                                          cv2.NORM_MINMAX, dtype=cv2.CV_8U)

            if len(display_frame.shape) == 2:
                display_frame = cv2.cvtColor(display_frame,
                                             cv2.COLOR_GRAY2BGR)

            # Enlarge so the interaction is easy to see
            big = cv2.resize(display_frame, None,
                             fx=SAVE_UPSCALE, fy=SAVE_UPSCALE,
                             interpolation=cv2.INTER_NEAREST)

            # Detection strip
            cv2.rectangle(big,
                          (ROI_X * SAVE_UPSCALE, ROI_Y * SAVE_UPSCALE),
                          ((ROI_X + ROI_WIDTH) * SAVE_UPSCALE,
                           (ROI_Y + ROI_HEIGHT) * SAVE_UPSCALE),
                          COLOR_ROI_IDLE, 1)

            # Mark each detected interaction, with some padding
            boxes = FRAME_BOXES.get(peak_frame, [])
            pad = 3

            for (bx, by, bw, bh) in boxes:
                cv2.rectangle(
                    big,
                    ((bx - pad) * SAVE_UPSCALE, (by - pad) * SAVE_UPSCALE),
                    ((bx + bw + pad) * SAVE_UPSCALE,
                     (by + bh + pad) * SAVE_UPSCALE),
                    COLOR_ROI_PEAK, 2
                )

            cv2.putText(big,
                        f"Event {rank}: Frames {start + 1}-{end + 1}",
                        (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        COLOR_TEXT, 1)

            cv2.putText(big,
                        f"Peak: {peak_frame + 1}  "
                        f"Area: {peak_score:.2f}%  "
                        f"Regions: {len(boxes)}",
                        (8, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        COLOR_TEXT, 1)

            filename = (f"event_{rank:03d}_frames_{start + 1}-{end + 1}_"
                        f"peak_{peak_frame + 1}.png")
            cv2.imwrite(os.path.join(OUTPUT_FOLDER, filename), big)

            writer.writerow([rank, start + 1, end + 1,
                             peak_frame + 1, f"{peak_score:.4f}",
                             len(boxes)])

            if rank % 25 == 0 or rank == len(events):
                print(f"Saved {rank} / {len(events)} events")

    print(f"\nResults saved to: {OUTPUT_FOLDER}")
    print(f"CSV file: {csv_path}")


# ============================================================
# PLAYBACK EVENT HELPERS
# ============================================================

def build_playback_events(events):
    """
    Analysis events are ranked by activity. For playback we need them
    in time order so the live counter climbs 1, 2, 3 ... as the video
    plays. Each entry keeps its analysis rank so it can be matched to
    particle_shock_events.csv.
    """
    rank_lookup = {
        (start, end, peak): rank
        for rank, (start, end, peak, _) in enumerate(events, start=1)
    }

    playback_events = []

    for order, (start, end, peak, score) in enumerate(
        sorted(events, key=lambda e: e[0]), start=1
    ):
        playback_events.append({
            "order": order,
            "rank": rank_lookup[(start, end, peak)],
            "start": start,
            "end": end,
            "peak": peak,
            "score": score,
        })

    return playback_events


def save_playback_report(playback_events, reached):
    """
    Cross-reference CSV: each event's frames plus whether playback
    actually displayed any frame of it.
    """
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)

    report_path = os.path.join(OUTPUT_FOLDER,
                               "particle_shock_playback_report.csv")

    with open(report_path, "w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Playback Order", "Analysis Rank (matches events CSV)",
                         "Start Frame", "End Frame", "Peak Frame",
                         "Peak Interaction Area (%)", "Playback Reached"])

        for ev in playback_events:
            writer.writerow([
                ev["order"],
                ev["rank"],
                ev["start"] + 1,
                ev["end"] + 1,
                ev["peak"] + 1,
                f"{ev['score']:.4f}",
                "Yes" if ev["order"] in reached else "No",
            ])

    return report_path


# ============================================================
# VIDEO PLAYBACK
# ============================================================

def play_video(images, events=None):
    """
    events: the list returned by analyze_video(). When provided, the
    playback shows a live event counter, boxes around each detected
    interaction, and highlights the strip while inside an event,
    then prints/saves a final tally.
    """

    WINDOW_NAME = "MRAW Playvideo"

    playback_events = build_playback_events(events) if events else []
    total_events = len(playback_events)
    starts = [ev["start"] for ev in playback_events]

    # Playback order numbers of events that were actually displayed
    reached = set()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 1024, 768)

    print("\n--- CONTROLS ---")
    print("• Press [SPACEBAR] to Pause / Play")
    print("• Press [s] to Slow down")
    print("• Press [f] to Speed up")
    print("• Press [r] to Rewind 100 frames")
    print("• Press [q] to Stop the program")

    frame_idx = 0
    paused = False
    total_frames = get_total_frames(images)
    delay = 10

    while frame_idx < total_frames:

        # Check if window was closed
        if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            break

        frame = images[frame_idx]

        display_frame = cv2.normalize(frame, None, 0, 255,
                                      cv2.NORM_MINMAX, dtype=cv2.CV_8U)

        if len(display_frame.shape) == 2:
            display_frame = cv2.cvtColor(display_frame, cv2.COLOR_GRAY2BGR)

        # Numbers computed during analysis, so they stay correct
        # while paused or after a rewind.
        activity_score = FRAME_SCORES.get(frame_idx, 0.0)
        boxes = FRAME_BOXES.get(frame_idx, [])

        # ----------------------------------------------------
        # Where are we relative to the detected events?
        # started = how many events have begun at or before this frame
        # ----------------------------------------------------
        started = bisect_right(starts, frame_idx)
        current_event = None

        if started > 0 and frame_idx <= playback_events[started - 1]["end"]:
            current_event = playback_events[started - 1]
            reached.add(current_event["order"])

        # Strip color: red idle, green in event, yellow on peak frame
        roi_color = COLOR_ROI_IDLE
        roi_thickness = 1

        if current_event is not None:
            roi_color = COLOR_ROI_EVENT
            roi_thickness = 2

            if frame_idx == current_event["peak"]:
                roi_color = COLOR_ROI_PEAK

        cv2.rectangle(display_frame,
                      (ROI_X, ROI_Y),
                      (ROI_X + ROI_WIDTH, ROI_Y + ROI_HEIGHT),
                      roi_color, roi_thickness)

        # Box around each detected interaction
        for (bx, by, bw, bh) in boxes:
            cv2.rectangle(display_frame,
                          (bx - 2, by - 2),
                          (bx + bw + 2, by + bh + 2),
                          COLOR_REGION, 1)

        # Frame counter
        cv2.putText(display_frame,
                    f"Frame: {frame_idx + 1:,} / {total_frames:,}",
                    (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.35, COLOR_TEXT, 1)

        # Interaction area
        cv2.putText(display_frame,
                    f"Interaction: {activity_score:.2f}%  "
                    f"regions: {len(boxes)}",
                    (5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.35, COLOR_TEXT, 1)

        # Live event counter
        if total_events > 0:
            cv2.putText(display_frame,
                        f"Event: {started} / {total_events}",
                        (5, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                        COLOR_TEXT, 1)

            if current_event is not None:
                label = (f"IN EVENT {current_event['order']} "
                         f"({current_event['start'] + 1}-"
                         f"{current_event['end'] + 1})")

                if frame_idx == current_event["peak"]:
                    label += "  PEAK"

                cv2.putText(display_frame, label,
                            (5, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                            COLOR_ROI_EVENT, 1)

        cv2.imshow(WINDOW_NAME, display_frame)

        key = cv2.waitKey(delay) & 0xFF

        if key == ord("q"):
            print("Program stopped by user.")
            break

        elif key == ord(" "):
            paused = not paused
            if paused:
                print("Paused. Press Spacebar again to resume.")

        elif key == ord("s"):
            delay = min(delay + 10, 500)
            print(f"Playback delay: {delay} ms")

        elif key == ord("f"):
            delay = max(delay - 10, 1)
            print(f"Playback delay: {delay} ms")

        elif key == ord("r"):
            frame_idx = max(frame_idx - 100, 0)
            print(f"Rewound to frame {frame_idx + 1}")

        # If paused, don't advance
        if paused:
            continue

        frame_idx += 1

    cv2.destroyAllWindows()

    # --------------------------------------------------------
    # Final tally
    # --------------------------------------------------------
    print("\n========================================")
    print("PLAYBACK TALLY")
    print("========================================")

    if total_events == 0:
        print("No analyzed events were supplied to playback.")
    else:
        print(f"Events found in analysis: {total_events}")
        print(f"Events reached in playback: {len(reached)} / {total_events}")

        missed = [ev for ev in playback_events if ev["order"] not in reached]
        if missed:
            print("Not reached (playback ended or was skipped past):")
            for ev in missed:
                print(f"  Event {ev['order']}: "
                      f"frames {ev['start'] + 1}-{ev['end'] + 1}")

        report_path = save_playback_report(playback_events, reached)
        print(f"Cross-reference CSV: {report_path}")

    print("Video finished.")

    return reached


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":
    print("video_player.py is designed to be called from main.py.")
    print("Run main.py to load the encrypted video.")