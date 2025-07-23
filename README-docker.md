# Dockerized transcription server
This process is tested under rootless podman, but using it under real docker
should be similar.

## Building/running the docker container

Building the container should be pretty straightforward
```
podman build -t transcription_rest .
```

When finished, the container should be around 7.5G  

## Running

Four things are needed for the container to run properly:
* the `/data` directory must be bound to the container.  This contains the logs
  and the user credentials
* `/data/user.txt` needs to contain the credentials for the users.  The 
  container will fail to start if this is missing
* the `/models` directory must be bound.  This is where all of the models will
  be downloaded to as they are needed.  A full set of models weighs in at around
  37G
* Port 3000 must be remapped to something relevant for your system.

This sample command will start the container with CPU transcoding:
```
podman run --rm \
  -v /srv/scratch/transcription_poc/models:/models:rw,Z \
  -v /srv/scratch/transcription_poc/data:/data:rw,Z \
  -p 8127:3000 localhost/transcription_rest
```

Enabling CUDA is a little more complex -- the device and the libraries have to
be exposed to the container.  The Nvidia Container Toolkit will provide most
of the heavy lifting (note:  it will need to be reconfigured if your podman
version changes) -- but it doesn't necessarily work out-of-the-box.

When everything is working, a command like this should run without error:
```
podman run --rm -it \
  --device nvidia.com/gpu=all \
  -v /srv/scratch/transcription_poc/models:/models:rw,Z \
  -v /srv/scratch/transcription_poc/data:/data:rw,Z \
  -p 8127:3000 localhost/transcription_rest /usr/bin/nvidia-smi
```

If it does, then you can start the container like this:
```
podman run --rm \
  --device nvidia.com/gpu=all \
  -v /srv/scratch/transcription_poc/models:/models:rw,Z \
  -v /srv/scratch/transcription_poc/data:/data:rw,Z \
  -p 8127:3000 localhost/transcription_rest
```

However, if you get an error like

```
Failed to initialize NVML: Insufficient Permissions
```

You'll need to make sure that the card (`/dev/nvidia0` and related files) can be
read by the rootless user, but that may not be enough.

On our server, the `/dev` nodes are present, but they have bogus permisions in
the guest:
```
-??????????  ? ?      ?            ?            ? nvidia-modeset
-??????????  ? ?      ?            ?            ? nvidia-uvm
-??????????  ? ?      ?            ?            ? nvidia-uvm-tools
-??????????  ? ?      ?            ?            ? nvidia0
-??????????  ? ?      ?            ?            ? nvidiactl
```

on the host system:
```
crw-rw-rw-. 1 root root 195,   0 Jun  1 07:36 /dev/nvidia0
crw-rw-rw-. 1 root root 195, 255 Jun  1 07:36 /dev/nvidiactl
crw-rw-rw-. 1 root root 195, 254 Jun  1 07:36 /dev/nvidia-modeset
crw-rw-rw-. 1 root root 236,   0 Jun  1 07:58 /dev/nvidia-uvm
crw-rw-rw-. 1 root root 236,   1 Jun  1 07:58 /dev/nvidia-uvm-tools
```

Turning off selinux labeling seems to do the trick.  This kind of makes sense
because the container is a debian 12 container and the host is rockylinux 8

```
podman run --security-opt=label=disable --rm  --device nvidia.com/gpu=all \
  -v /srv/scratch/transcription_poc/models:/models:rw,Z \
  -v /srv/scratch/transcription_poc/data:/data:rw,Z \
  -p 8127:3000 localhost/transcription_rest
```
