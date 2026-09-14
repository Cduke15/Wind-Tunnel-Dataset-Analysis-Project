# Wind-Tunnel-Dataset-Analysis-Project
Our senior project repository: Colby Duke and Jocelyn Ruiz.

Hello! We've designed a program that can read cih and mraw data files because we lacked a tool to do so - we use two things primarily with python code: pyMRAW and OpenCV.

pyMRAW reads the raw data (frame by frame) and opencv turns it into a viewable video.

Links to them are here: 
https://pypi.org/project/pyMRAW/
https://opencv.org/

~~~

**INSTRUCTIONS for our MRAW data reader program to run**

You MUST have Python installed via the latest Python installer, not just through your IDE.
You can get the latest Python extension here: https://www.python.org/downloads/

You run this line in a fresh terminal: python -m pip install pyMRAW opencv-python

Once that is complete you select a folder within your IDE to open from, placing both the cih and mraw files within. Depending on your IDE interface, you may be able to simply put them within your project folder so long as it can view it.

You then make a Python file named Play_video.py (or whatever name you may like). 

You put this code in and change the header file to one of cih files, not the MRAW files. NOTE: you must have the MRAW file of the same exact name of the cih for it to read it!

Once that is done, simply run and the program will start. A video pop-up should show up titled 'MRAW Playback' at which you can then press 'Space' to pause/resume and 'q' to quit when you are done viewing the data.

Overall this program is designed to read and run cih and mraw files - very simple and fast!