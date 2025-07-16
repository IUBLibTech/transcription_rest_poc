#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR

source .venv/bin/activate

case $1 in 
    dev)
        fastapi dev --host 0.0.0.0 --port 8125 --reload transcription_rest/transcription_rest.py
    ;;
    prod)
        fastapi run --host 0.0.0.0 --port 8125  transcription_rest/transcription_rest.py
    ;;
    *)
        echo Usage: $0 "[prod|dev]"
    ;;
esac
