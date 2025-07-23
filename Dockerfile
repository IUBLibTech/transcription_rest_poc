#
# Build a container for this monstrosity
#

#
# The first stage is a base debian install with the nvidia development
# environment
#
FROM debian:12 AS cuda_environment
RUN \
    apt-get update && \
    apt-get install -y gcc software-properties-common cmake git wget && \
    add-apt-repository -y contrib && \
    apt-get update && \
    wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb && \
    dpkg -i cuda-keyring_1.1-1_all.deb && \
    apt update && \
    apt-get install -y cuda-toolkit libcuda1

#
# Build whisper.cpp with CUDA support
#
FROM cuda_environment AS whispercpp_build
ENV PATH="/usr/local/cuda/bin:$PATH"
ENV LD_LIBRARY_PATH="/usr/local/cuda/lib64:$LD_LIBRARY_PATH"
RUN \
    git clone https://github.com/ggml-org/whisper.cpp.git && \
    cd whisper.cpp && \
    git checkout v1.7.6 && \
    cmake -B build -DGGML_CUDA=1 -DCMAKE_CUDA_ARCHITECTURES=all-major && \
    cmake --build build -j --config Release
    
#
# Build the generic container 
#
FROM debian:12 AS rest_server
COPY transcription_server /rest_server/transcription_server
COPY requirements.txt /rest_server
COPY --from=whispercpp_build \
    /whisper.cpp/build/bin/whisper-cli \
    /whisper.cpp/build/src/libwhisper.so.1 \
    /whisper.cpp/build/ggml/src/libggml.so \
    /whisper.cpp/build/ggml/src/libggml-base.so \
    /whisper.cpp/build/ggml/src/libggml-cpu.so \
    /whisper.cpp/build/ggml/src/ggml-cuda/libggml-cuda.so \
    /rest_server/whisper.cpp/

# CUDA Runtime -- these don't come in via cdi?
COPY --from=whispercpp_build \
    /usr/local/cuda/lib64/libcudart.so.12 \
    /usr/local/cuda/lib64/libcublas.so.12 \
    /usr/local/cuda/lib64/libcublasLt.so.12 \
    /rest_server/whisper.cpp/

COPY docker_entry.sh /rest_server
COPY <<EOF /server.conf
---
server:
  port: 3000
  host: 0.0.0.0
    
files:
  database: /data/transcription.db
  log_dir: /data
  models_dir: /models
  users: /data/users.txt
EOF

RUN \
    apt-get update && \
    apt-get install -y python3 python3-pip python3-venv ffmpeg && \
    cd /rest_server && \
    mkdir /data /models && \
    python3 -mvenv .venv && \
    . .venv/bin/activate && \
    pip install -r requirements.txt && \
    rm -rf /root/.cache

EXPOSE 3000/tcp
CMD /rest_server/docker_entry.sh
