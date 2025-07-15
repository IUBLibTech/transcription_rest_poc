#!/bin/env python3

import sys
from whisper import _MODELS, _download

root = sys.path[0] + "/openai-whisper"
for name, url in _MODELS.items():
    print(f"Model {name} downloaded to {_download(url, root, False)}")
