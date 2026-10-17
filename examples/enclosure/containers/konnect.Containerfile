# KiCad 10 with its symbol, footprint and 3D libraries (the -full image), plus the
# Konnect MCP server release binary, both pinned. Build, then pin by image ID:
#   podman build -t konnect -f konnect.Containerfile .
#   podman image inspect konnect --format '{{.Id}}'
FROM docker.io/kicad/kicad:10.0.6-full@sha256:e36e29b5f4a638a1a7238eba3d2fcbc8e061ffed1e99a8f39cb722706c94a58e

USER root
ADD --checksum=sha256:9c9d28e7d905d8e8519339a78890193f252bc8134993349b40d80e3a67b93512 \
    https://github.com/mixelpixx/Konnect/releases/download/v0.13.0/konnect-v0.13.0-x86_64-unknown-linux-gnu.tar.gz \
    /tmp/konnect.tar.gz
RUN tar -xzf /tmp/konnect.tar.gz -C /usr/local/bin konnect \
 && chmod 755 /usr/local/bin/konnect \
 && rm /tmp/konnect.tar.gz
