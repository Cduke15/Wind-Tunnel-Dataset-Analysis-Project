# Copyright 2026 Colby Duke / Jocelyn Ruiz / University of Tennessee Martin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://apache.org
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import json # Needed for secure config - updated to this
import os # Helps manage the pathing
import sys
import hmac # Used for password verification checks
import getpass # Safely hides password typing in terminal
import numpy as np # works with decryption
import video_player # The original tool - needed here!

# Cryptography Python tools - used here for AES-128, SHA-256, and PBKDF2, helps with heavy lifting
# Using this instead of Fernet due to the massive file size of the data
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

# Every dataset gets its OWN sub-folder inside particle_shock_events
# (event pictures, CSVs, strip settings), named after the dataset, so
# analyzing a new dataset never overwrites another one.
RESULTS_DIR = os.path.join(SCRIPT_DIR, "particle_shock_events",
                           HEADER_NAME.replace(".cih", ""))

# Datasets whose detection strip is FIXED to an exact position [x, y, width, height]
# instead of being placed automatically. The original dataset keeps its original
# strip, so its detection is identical to before. Other datasets use the automatic
# placement on the black block's left face.
FIXED_ROI_BY_DATASET = {
    "Lash_HollowCyl_M4_20190411_Run18_3D.cih": [214, 20, 20, 130],
}

# Frames where YOU saw interactions, per dataset (used for the calibration report).
# Datasets not listed here simply skip the calibration report.
KNOWN_FRAMES_BY_DATASET = {
    "Lash_HollowCyl_M4_20190411_Run18_3D.cih": [552, 801, 807, 2230, 2290, 2477, 2551],
}


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


# Reads the ORIGINAL (unencrypted) .mraw one frame at a time, so the whole
# video is never held in memory. Uses pyMRAW only to parse the .cih header.
class RawMRAWSource:
    def __init__(self, cih_path):
        import pyMRAW

        # Different pyMRAW versions name the header parser differently
        loader = getattr(pyMRAW, "get_cih", None) or getattr(pyMRAW, "load_info")
        info = loader(cih_path)

        self.h = int(info["Image Height"])
        self.w = int(info["Image Width"])
        self.n = int(info["Total Frame"])
        self.bit = int(info["Color Bit"])
        self.mraw_path = os.path.splitext(cih_path)[0] + ".mraw"

        if self.bit == 8:
            self.dtype = np.dtype(np.uint8)
            self.frame_bytes = self.h * self.w
        elif self.bit == 16:
            self.dtype = np.dtype(np.uint16)
            self.frame_bytes = self.h * self.w * 2
        elif self.bit == 12:
            # 12-bit data is packed: 2 pixels per 3 bytes. Unpacked to uint16.
            self.dtype = np.dtype(np.uint16)
            self.frame_bytes = self.h * self.w * 3 // 2
        else:
            raise ValueError(f"Unsupported bit depth: {self.bit}")

        # Guard against a truncated file
        available = os.path.getsize(self.mraw_path) // self.frame_bytes
        if available < self.n:
            print(f"Warning: header says {self.n} frames but the file only "
                  f"holds {available}. Using {available}.")
            self.n = available

        self.shape = (self.n, self.h, self.w)
        self.f = open(self.mraw_path, "rb")

    def __getitem__(self, idx):
        self.f.seek(idx * self.frame_bytes)
        raw = self.f.read(self.frame_bytes)

        if self.bit == 12:
            b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.uint16)
            first = (b[:, 0] << 4) + (b[:, 1] >> 4)
            second = ((b[:, 1] & 15) << 8) + b[:, 2]
            return np.stack([first, second], axis=1).reshape(self.h, self.w)

        return np.frombuffer(raw, dtype=self.dtype).reshape(self.h, self.w)

    def close(self):
        self.f.close()


# This stream class manages the on-demand frame tracking and random IV alignment
class EncryptedMRAWStream:
    def __init__(self, cih_path, mraw_path, key):
        with open(cih_path, "r") as f:
            self.meta = json.load(f)
            
        self.shape = tuple(self.meta["shape"]) # This exposes a standard shape tuple to the player
        self.dtype = np.dtype(self.meta["dtype"])
        
        # Exposing total_frames value correctly using structural assignment matching player line 28
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
        # Wrap at 128 bits, the same way the CTR mode itself does
        current_iv = ((iv_int + counter_offset) % (1 << 128)).to_bytes(16, byteorder="big")
        
        # Initialize cipher for just this single frame index
        cipher = Cipher(algorithms.AES(self.key), modes.CTR(current_iv), backend=default_backend())
        decryptor = cipher.encryptor() # CTR decryption uses the same architecture pattern
        
        decrypted = decryptor.update(ciphertext) + decryptor.finalize()
        return np.frombuffer(decrypted, dtype=self.dtype).reshape(self.shape[1:])

    def close(self):
        self.f.close()


def run_encryption_flow(password_input: bytes): # Reads the raw files here
    print("Opening original video... Please wait.") 
    try: 
        source = RawMRAWSource(HEADER_FILE)
        print(f"Success! {source.n:,} frames, {source.w}x{source.h}, "
              f"{source.bit}-bit. Streaming frame by frame (low memory).")
    except Exception as e: 
        print(f"Error opening original raw file: {e}")
        sys.exit(1)

    # Generate a fresh, globally unique 16-byte salt for this file execution context
    random_salt = os.urandom(16)
    key = generate_key_from_password(password_input, random_salt)

    # Generate a verification tag tied to this specific password key
    auth_tag = calculate_auth_tag(key)

    meta_dict = {
        "shape": list(source.shape), 
        "dtype": str(source.dtype),
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
    try:
        with open(TARGET_MRAW, "wb") as f:
            f.write(random_iv) # Store the random IV inside the first 16 bytes safely
            
            # One frame at a time: memory use stays flat for any dataset size
            for i in range(source.n):
                f.write(encryptor.update(source[i].tobytes()))

                if i % 2000 == 0 and i > 0:
                    print(f"Encrypted {i:,} / {source.n:,} "
                          f"({i / source.n * 100:.1f}%)")

            f.write(encryptor.finalize())
    finally:
        source.close()
        
    print("Video encrypted! Re-run the program to view it.\n")


def run_playback_flow(password_input: bytes):
    print("Attempting to load secure video... Please wait.") 
    video_stream = None
    try: 
        # WRONG PASSWORD CHECK: Compare calculated tag with stored tag
        with open(TARGET_CIH, "r") as f:
            meta = json.load(f)
            
        # Extract the file's custom salt and turn it back into raw bytes
        stored_salt = bytes.fromhex(meta["salt_hex"])
        key = generate_key_from_password(password_input, stored_salt)
        
        calculated_tag = calculate_auth_tag(key)
        if not hmac.compare_digest(str(meta.get("auth_tag")), calculated_tag):
            print("\n Access denied.")
            sys.exit(1)

        # Create our streaming reader to extract and decrypt frames sequentially or via seeking
        video_stream = EncryptedMRAWStream(TARGET_CIH, TARGET_MRAW, key)
        print("Success! Secure video loaded.") 

    except Exception as e: 
        print(f"Error reading or decrypting file: {e}") 
        sys.exit(1)

    try:
        #Per-dataset results folder + detection strip placed on the black block's left face
        video_player.setup_dataset(video_stream, RESULTS_DIR,
                                   KNOWN_FRAMES_BY_DATASET.get(HEADER_NAME, []),
                                   FIXED_ROI_BY_DATASET.get(HEADER_NAME))

        #Analyze the video
        # Send our stream object straight into your clean playback engine
        events = video_player.analyze_video(video_stream)
        #Save the detected events
        video_player.save_interaction_events(video_stream, events)
        
        # Play the video
        video_player.play_video(video_stream, events)
    finally:
        #close the encrypted video stream, even if something goes wrong
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
