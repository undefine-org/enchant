# Experimental scene renderer

Compose deterministic scenes in BL, inspect named objects and sample any frame.
The scene API and example tools are experimental. Use this preview for local
studies; data formats and rendering behavior may change between releases.

The generic studies cover editorial SVG, measured postcards, clip scheduling,
a camera-led atlas and persistent keyed transformations. The local postcard
studio offers selected-frame preview and a separate export worker. Font files
and OFL licenses live in `assets/fonts`. Commercial films and client assets are
kept outside this example.

From the repository root, enter the pinned graphics tool shell:

```sh
nix-shell nix/scene-tools.nix
scripts/bl-mem
systemd-run --user --collect --wait --pipe --working-directory="$PWD" \
  --property=MemoryMax=4G --property=MemorySwapMax=0 \
  ./bin/bl test test/bl/scene/core_test.bl test/bl/scene/camera_test.bl
```

This uses the checkout's normal SDK selection and compiler path. Graphics tools
are optional dependencies: Python 3, librsvg/Pango/Cairo, Fontconfig and FFmpeg.
The shell pins them with the repository's package lock. Text shaping uses the
four packaged font files and reports font hashes and native library versions.

Build a postcard with the same process cap:

```sh
systemd-run --user --collect --wait --pipe --working-directory="$PWD" \
  --property=MemoryMax=4G --property=MemorySwapMax=0 \
  ./bin/bl run examples/scene-renderer/postcard.bl -- /tmp/bl-postcard
```

For the local editor, run `examples/scene-renderer/studio.sh /tmp/bl-postcard-studio`
under that cap and open `http://127.0.0.1:4048`. Stop the owning command when
finished. The wrapper uses a private runtime directory and cleans up its workers.
One publisher owns each output directory. A completed revision is published by
rename; the manifest selects its frame directory. Failed work retains its
previous publication. Export selects an accepted revision independently of
preview requests.

BL owns geometry, composition and time. The Python workers execute shaped paths,
rasterization and encoding. JavaScript transports evaluated frames and editor
requests. The graphics tests cover measured text, selected samples, identities
and temporal boundaries. Browser interaction and full-film quality require
separate checks; they are not implied by a passing language test batch.

Read `priv/lib/scene/README.md` for the public API and its limits. PNG output
identifies the chosen backend/font inputs. H.264 video is silent, lossy and
subject to encoder differences across tool versions. Path topology, readable
text size and finite atlas sampling density remain explicit author choices.
