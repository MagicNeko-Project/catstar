# Media processing wrappers
# Heavy heavy hitters are autoloaded

extractopus() { extractaudio "$1" "opus" }
extractm4a() { extractaudio "$1" "m4a" }

# Stub for simple ffmpeg calls if needed, but primary logic is in functions/ directory
