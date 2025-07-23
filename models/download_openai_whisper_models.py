#!/bin/env python3

import sys
from whisper import _MODELS, _download
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("model_root", help="Root directory for openai-whisper models",
                    default=sys.path[0] + "/openai-whisper")
args = parser.parse_args()

for name, url in _MODELS.items():
    print(f"Model {name} downloaded to {_download(url, args.model_root, False)}")
