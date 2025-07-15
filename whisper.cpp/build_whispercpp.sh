#!/bin/bash
#
# Download and build whisper.cpp
#
# Note: on rhel 8 systems you need GCC 12+ for it to build.  
# Install gcc-toolset-12 and then run
#    scl enable gcc-toolset-12 bash
# That will give you a shell where gcc is gcc12.
#
# You may also have to set CUDACXX to point to nvcc.

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

cd $SCRIPT_DIR

git clone https://github.com/ggml-org/whisper.cpp.git
pushd whisper.cpp
git checkout v1.7.6

# choose to build CUDA if it's available, otherwise CPU
if nvcc --version > /dev/null; then
    BUILD_OPTIONS="-DGGML_CUDA=1"
else
    echo "nvcc not found.  If you have NVIDIA hardware, set PATH to find nvcc"
    BUILD_OPTIONS=""
fi
rm -rf build
cmake -B build $BUILD_OPTIONS && \
    cmake --build build -j --config Release

popd

# make some symlinks to stuff in whisper.cpp so the tools can easily find
# what we need
ln -s whisper.cpp/build/bin/whisper-cli .
ln -s whisper.cpp/models/download-ggml-model.sh .
ln -s whisper.cpp/models/download-vad-model.sh .

