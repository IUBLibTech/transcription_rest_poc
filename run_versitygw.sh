#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source $SCRIPT_DIR/versitygw_environment.sh

/srv/shared/versitygw/versitygw-v1.0.15.sif \
    --debug \
    posix "$@"
