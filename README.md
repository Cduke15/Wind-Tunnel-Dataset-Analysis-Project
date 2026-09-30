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

If you need them, run this command in a fresh terminal: python -m pip install pyMRAW opencv-python cryptography
If you only need one, simply run: pip install (library)

Once you have all three libraries above, select a folder within your IDE to open from, placing both the cih and mraw files within. Depending on your IDE interface, you may be able to simply put them within your project folder so long as it can view it.

You then place the source files, video_player.py and main.py, inside your project folder.

Within the main.py, change the header file to one of cih files' names, not the MRAW files. NOTE: you must have the MRAW file of the same exact name of the cih for it to read it!

Once that is done, simply run the main.py and the program will start. It will ask you for a password for the file. Enter one you can remember!

It will then go through and encrypt the data file, making a secure copy in case of data loss. This allows you to retain your original copy and delete it if you wish.

After this, re-run the program and enter the password you put in to view the playback. If it is correct, it will run!

A video pop-up should then show up titled 'MRAW Playvideo' at which you can then press:
- 'Space' to pause/resume
- 'q' to quit when you are done viewing the data.
- 's' to slow down
- 'f' to speed up
- 'r' to rewind by 100 frames 

~~~

Overall this program is designed to read, encrypt, authenticate, and run cih and mraw files!
