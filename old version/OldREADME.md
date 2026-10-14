**INSTRUCTIONS for our original version of the MRAW data reader program to run - this does not have the auto-shock tracker information within it**

~~~

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
