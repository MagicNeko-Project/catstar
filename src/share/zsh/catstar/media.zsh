# Catstar Media Utilities
# -----------------------------------------------------------------------------
# This file provides wrappers for media processing (audio extraction, video
# conversion, etc.) leveraging FFmpeg.
# -----------------------------------------------------------------------------

# --- Audio Extraction ---
# These functions use the autoloaded 'extractaudio' function.

# Extract audio as Opus (high quality, modern codec)
extractopus() { 
  extractaudio "$1" "opus" 
}

# Extract audio as M4A (high compatibility, AAC)
extractm4a() { 
  extractaudio "$1" "m4a" 
}

# --- Future Media Logic ---
# Add more media-related wrappers below as needed.
