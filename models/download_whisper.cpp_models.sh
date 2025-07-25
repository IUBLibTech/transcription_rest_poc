#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# download the models into the models directory
mkdir whisper.cpp

for model in tiny tiny.en tiny-q5_1 tiny.en-q5_1 tiny-q8_0 \
             base base.en base-q5_1 base.en-q5_1 base-q8_0 \
             small small.en small.en-tdrz small-q5_1 small.en-q5_1 small-q8_0 \
             medium medium.en medium-q5_0 medium.en-q5_0 medium-q8_0 \
             large-v1 \
             large-v2 large-v2-q5_0 large-v2-q8_0 \
             large-v3 large-v3-q5_0 large-v3-turbo large-v3-turbo-q5_0 large-v3-turbo-q8_0; do
    $SCRIPT_DIR/../whisper.cpp/download-ggml-model.sh $model whisper.cpp
done
