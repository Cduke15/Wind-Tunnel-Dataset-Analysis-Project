import cv2
import pyMRAW

# Put the exact name of your .cih or .cihx file here
HEADER_FILE = "Garner_HC_M4_Schlieren_BL Campaign_Run6_HCModel_2-26-2021_Cylinder_NoGap_rubbertrip_Won.cih" 

print("Attempting to load video... Please wait.")
try:
    images, info = pyMRAW.load_video(HEADER_FILE)
    print("Success! Video loaded.")
except Exception as e:
    print(f"Error loading file: {e}")
    exit()

WINDOW_NAME = 'MRAW Playback'
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

print("\n--- CONTROLS ---")
print("• Press [SPACEBAR] to Pause / Play")
print("• Press [Q] to Stop the program entirely\n")

frame_idx = 0
paused = False
total_frames = images.shape[0]

# Using a while loop gives us absolute control over the timeline frame-by-frame
while frame_idx < total_frames:
    # Check if the user clicked the window's 'X' button
    if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
        break
        
    frame = images[frame_idx]
    
    # Lighten video
    bright_frame = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    cv2.imshow(WINDOW_NAME, bright_frame)
    
    # Check keyboard inputs
    key = cv2.waitKey(10) & 0xFF
    
    if key == ord('q'):  # Stop the program entirely
        print("Program stopped by user.")
        break
    elif key == ord(' '):  # Spacebar toggles pause state
        paused = not paused
        if paused:
            print("Paused. Press Spacebar again to resume, or Q to quit.")
            
    # If paused, keep waiting on the exact same frame index
    if paused:
        continue
        
    # Advance to next frame if not paused
    frame_idx += 1

print("Video sequence finished. Window left active for inspection.")
print("To completely exit the Python script run, click the Terminal and press Ctrl+C.")
