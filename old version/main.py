# Important: This is the main.py for the old version WITHOUT the auto-tracker, in case you need to simply view the .cih/.mraw data by itself


import json # Needed for secure config - updated to this
import os # Helps manage the pathing
import hmac # Used for password verification checks
import getpass # Safely hides password typing in terminal
import numpy as np # works with decryption
import video_player # The original tool - needed here!

# Cryptography Python hazmat tools - used here for AES-128, SHA-256, and PBKDF2, helps with heavy lifting
# Using this instead of Fernet due to the massive file size of the data
# Becareful with these - they can be dangerous if used incorrectly!
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Automatically find the exact folder where this script is saved
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Put the exact name of your .cih file here
HEADER_NAME = "Lash_HollowCyl_M4_20190411_Run18_3D.cih" 

# Helps prevent issues with the paths
HEADER_FILE = os.path.join(SCRIPT_DIR, HEADER_NAME)
TARGET_CIH = os.path.join(SCRIPT_DIR, HEADER_NAME.replace(".cih", "_secure.cih"))
TARGET_MRAW = os.path.join(SCRIPT_DIR, HEADER_NAME.replace(".cih", "_secure.mraw"))


# Make a password which goes into the file
def generate_key_from_password(password: bytes, unique_salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=16, # AES-128 requires exactly 16 bytes
        salt=unique_salt, # randomizes salt
        iterations=100000,
        backend=default_backend()
    )
    return kdf.derive(password)


# Helper function to generate a quick verification token for password checking
def calculate_auth_tag(key: bytes) -> str:
    return hmac.new(key, b"MRAW_VALID", "sha256").hexdigest()


# This stream class manages the on-demand frame tracking and random IV alignment
class EncryptedMRAWStream:
    def __init__(self, cih_path, mraw_path, key):
        with open(cih_path, "r") as f:
            self.meta = json.load(f)
            
        self.shape = tuple(self.meta["shape"]) # This exposes a standard shape tuple to the player
        self.dtype = np.dtype(self.meta["dtype"])
        
        # FIXED: Exposing total_frames value correctly using structural assignment matching player line 28
        self.total_frames = self.shape[0]
        
        # Calculate exactly how many bytes are in a single frame
        self.frame_bytes_size = int(np.prod(self.shape[1:]) * self.dtype.itemsize)
        
        # Open file and extract random 16-byte IV from the very beginning
        self.f = open(mraw_path, "rb")
        self.iv = self.f.read(16)
        self.key = key

    # This magic method intercepts player calls like `images[frame_idx]` and decrypts it right here in main!
    def __getitem__(self, frame_idx):
        # Calculate exact file position where this frame's ciphertext starts
        frame_offset = 16 + (frame_idx * self.frame_bytes_size)
        self.f.seek(frame_offset)
        ciphertext = self.f.read(self.frame_bytes_size)
        
        # Calculate AES-CTR counter block changes for precise seek offsets
        counter_offset = (frame_idx * self.frame_bytes_size) // 16
        iv_int = int.from_bytes(self.iv, byteorder="big")
        current_iv = (iv_int + counter_offset).to_bytes(16, byteorder="big")
        
        # Initialize cipher for just this single frame index
        cipher = Cipher(algorithms.AES(self.key), modes.CTR(current_iv), backend=default_backend())
        decryptor = cipher.encryptor() # CTR decryption uses the same architecture pattern
        
        decrypted = decryptor.update(ciphertext) + decryptor.finalize()
        return np.frombuffer(decrypted, dtype=self.dtype).reshape(self.shape[1:])

    def close(self):
        self.f.close()


def run_encryption_flow(password_input: bytes): # Loads the raw files here
    print("Attempting to load original video... Please wait.") 
    try: 
        import pyMRAW
        images, info = pyMRAW.load_video(HEADER_FILE) 
        print("Success! Video loaded raw.") # Raw being insecure
    except Exception as e: 
        print(f"Error loading original raw file: {e}")
        exit() 

    # Generate a fresh, globally unique 16-byte salt for this file execution context
    random_salt = os.urandom(16)
    key = generate_key_from_password(password_input, random_salt)

    # Generate a verification tag tied to this specific password key
    auth_tag = calculate_auth_tag(key)

    meta_dict = {
        "shape": list(images.shape), 
        "dtype": str(images.dtype),
        "salt_hex": random_salt.hex(),
        "auth_tag": auth_tag # Saved to check for wrong passwords later
    }
    
    # Save the text metadata/blueprint to the secure .cih file copy
    print(f"Saving a secure copy of {TARGET_CIH}...")
    with open(TARGET_CIH, "w") as f:
        json.dump(meta_dict, f)

    print("Encrypting...")
    
    # Dynamically generate a secure, completely random IV for this tracking file
    random_iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CTR(random_iv), backend=default_backend())
    encryptor = cipher.encryptor()

    # Saves a secure copy, leaving the old intact (delete the old ones once the data is encrypted)
    # This is in case of data corruption - losing valuable data would be bad!
    print(f"Saving a secure copy of {TARGET_MRAW}...")
    with open(TARGET_MRAW, "wb") as f:
        f.write(random_iv) # Store the random IV inside the first 16 bytes safely
        
        # Loop target matches the exact number of frames in the dimension array
        for i in range(images.shape[0]):
            frame_bytes = images[i].tobytes()
            f.write(encryptor.update(frame_bytes))
        f.write(encryptor.finalize())
        
    print("Video encrypted! Re-run the program to view it.\n")


def run_playback_flow(password_input: bytes):
    print("Attempting to load secure video... Please wait.") 
    try: 
        # WRONG PASSWORD CHECK: Compare calculated tag with stored tag
        with open(TARGET_CIH, "r") as f:
            meta = json.load(f)
            
        # Extract the file's custom salt and turn it back into raw bytes
        stored_salt = bytes.fromhex(meta["salt_hex"])
        key = generate_key_from_password(password_input, stored_salt)
        
        calculated_tag = calculate_auth_tag(key)
        if meta.get("auth_tag") != calculated_tag:
            print("\n Access denied.")
            exit()

        # Create our streaming reader to extract and decrypt frames sequentially or via seeking
        video_stream = EncryptedMRAWStream(TARGET_CIH, TARGET_MRAW, key)
        print("Success! Secure video loaded.") 

    except Exception as e: 
        print(f"Error reading or decrypting file: {e}") 
        exit()

    # Send our stream object straight into your clean playback engine
    video_player.play_video(video_stream)
    video_stream.close()


if __name__ == "__main__":
    # Ensure BOTH secure files exist before trying to play them back
    if os.path.exists(TARGET_CIH) and os.path.exists(TARGET_MRAW):
        password_input = getpass.getpass("Enter password to PLAY video: ").encode()
        run_playback_flow(password_input)
    elif os.path.exists(HEADER_FILE):
        password_input = getpass.getpass("Create a password to ENCRYPT video: ").encode()
        run_encryption_flow(password_input)
    else:
        print(f"Error: Could not find your data files in {SCRIPT_DIR}")

