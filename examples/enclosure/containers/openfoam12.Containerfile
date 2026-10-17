# OpenFOAM Foundation 12 from its apt repository; the Foundation publishes no image
# after v11. Build, then pin the result by digest in enclosure.py:
#   podman build -t openfoam12 -f openfoam12.Containerfile .
#   podman image inspect openfoam12 --format '{{.Id}}'
FROM docker.io/library/ubuntu:24.04@sha256:f610ab94648195aa356059f5b41d6085c9d4d903c072430cdd1af7bdb646106b

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates wget gnupg software-properties-common \
 && wget -qO /etc/apt/trusted.gpg.d/openfoam.asc https://dl.openfoam.org/gpg.key \
 && add-apt-repository -y http://dl.openfoam.org/ubuntu \
 && apt-get update \
 && apt-get install -y --no-install-recommends openfoam12 \
 && rm -rf /var/lib/apt/lists/*
