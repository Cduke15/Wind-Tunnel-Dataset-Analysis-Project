import cv2 

import pyMRAW 


## Put the exact name of your .cih or .cihx file here ## 

HEADER_FILE = "Lash_HollowCyl_M4_20190411_Run18_3D.cih" 


print("Attempting to load video... Please wait.") 

try: 

    images, info = pyMRAW.load_video(HEADER_FILE) 

    print("Success! Video loaded.") 

except Exception as e: 

    print(f"Error loading file: {e}") 

    exit() 


WINDOW_NAME = 'MRAW Playvideo' 

cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL) 
cv2.resizeWindow(WINDOW_NAME, 1024, 768)

print("--- CONTROLS ---") 

print("• Press [SPACEBAR] to Pause / Play") 

print("• Press [s] to Slow down") 

print("• Press [f] to Speed up") 

print("• Press [r] to Rewind 100 frames")

print("• Press [q] to Stop the program entirely ") 


frame_idx = 0 

paused = False 

total_frames = images.shape[0] #get the total number of frames 

delay = 10 #Playback speed 


# Using a while loop gives us absolute control over the timeline frame-by-frame 

while frame_idx < total_frames: 

    # Check if the user clicked the window's 'X' button 

    if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1: 

        break 

        

    frame = images[frame_idx] 

    

    # Lighten video - some of the data was very dark 

    bright_frame = cv2.normalize( frame, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U ) 

    

    # Display the current frame / total frames 

    frame_text = f"Frame: {frame_idx +1} / {total_frames}" 

    cv2.putText( bright_frame, frame_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 255, 2 ) 

    

    #Display the frame 

    cv2.imshow(WINDOW_NAME, bright_frame) 

    

    # Check keyboard inputs 

    key = cv2.waitKey(delay) & 0xFF 

    if key == ord('q'): # Stop the program entirely 

        print("Program stopped by user.") 

        break 

    elif key == ord(' '): # Spacebar toggles pause state 

        paused = not paused 

        if paused: 

            print("Paused. Press Spacebar again to resume, or Q to quit.") 

    elif key == ord('s'): #increase the delay = slower playback 

        delay += 10 

        if delay > 500: 

            delay = 500 

        print(f"Playback delay: {delay} ms") 

    elif key == ord('f'): #decrease the delay = faster playback 

        delay -= 10 

        if delay < 1: 

            delay = 1 

        print(f"Playback delay: {delay} ms") 

    elif key == ord('r'): #rewind control - go back 100 frames
        # Rewind 100 frames
        frame_idx -= 100

        # Don't go below the first frame
        if frame_idx < 0:
            frame_idx = 0

        print("Rewound to frame {frame_idx + 1}")

        
    # If paused, keep waiting on the exact same frame 

    if paused: 

        continue 

        

    # Advance to next frame if not paused 

    frame_idx += 1 


cv2.destroyAllWindows() 

print("Video finished.")
