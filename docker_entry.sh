#!/bin/bash
source /rest_server/.venv/bin/activate

# do a quick sanity check and make sure the /data/users.txt file exists
if [ ! -e /data/users.txt ]; then
    echo "You must have a valid users.txt file in /data"
    exit 1
fi

# the libraries needed for whisper.cpp are in the whisper.cpp directory
export LD_LIBRARY_PATH=/rest_server/whisper.cpp:$LD_LIBRARY_PATH

exec /rest_server/transcription_server/main.py /server.conf