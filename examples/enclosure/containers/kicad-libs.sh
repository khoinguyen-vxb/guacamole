#!/bin/sh
# Copy the KiCad symbol and footprint libraries out of the pinned Konnect image,
# so agents can read them as a read-only project input instead of searching the
# host. Pass the image ID that enclosure.py pins:
#   examples/enclosure/containers/kicad-libs.sh sha256:6f3c9de2...
set -eu
image=$1
target=$(dirname "$0")/../kicad-libs
rm -rf "$target"
mkdir -p "$target"
container=$(podman create "$image")
trap 'podman rm -f "$container" >/dev/null' EXIT
for part in symbols footprints template/sym-lib-table template/fp-lib-table; do
    podman cp "$container:/usr/share/kicad/$part" "$target/"
done
echo "$image" > "$target/IMAGE"
