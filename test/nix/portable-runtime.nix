# Execute a real portable drop with no /nix/store visible to its receiver.
# The baseline supplies the declared glibc/C++/OTP runtime libraries as ordinary
# FHS files. SDK files and their integrity metadata are never rewritten here.
{ drop, erlang }:
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  runtime = pkgs.closureInfo {
    rootPaths = [ (builtins.storePath (toString erlang)) pkgs.glibc pkgs.stdenv.cc.cc.lib ];
  };
in (import ../../nix/bounded-build.nix {
  inherit pkgs;
  memoryMiB = 3072;
  diskMiB = 8192;
  cpuCount = 4;
  commandManager = true;
}) (pkgs.runCommand "beam-lisp-portable-runtime-control" {} ''
  receiver=/build/receiver
  trap 'status=$?; test ! -f "$out/receiver.log" || cat "$out/receiver.log"; exit "$status"' EXIT
  mkdir -p "$receiver"/{bin,usr/bin,lib,lib64,dev,proc,etc,root,tmp}
  cp ${pkgs.pkgsStatic.busybox}/bin/busybox "$receiver/bin/busybox"
  for applet in $("$receiver/bin/busybox" --list); do
    test "$applet" = busybox || ln -s busybox "$receiver/bin/$applet"
  done
  ln -s ../../bin/busybox "$receiver/usr/bin/env"
  while IFS= read -r package; do
    for directory in "$package/lib" "$package/lib64"; do
      test -d "$directory" || continue
      for library in "$directory"/*.so*; do
        test -f "$library" || continue
        name=$(basename "$library")
        if ! test -e "$receiver/lib/$name"; then
          cp -L "$library" "$receiver/lib/$name"
        fi
      done
    done
  done < ${runtime}/store-paths
  # The receiver baseline chooses the pinned current C/C++ ABI explicitly;
  # transitive packages may also reference an older libgcc with the same SONAME.
  for directory in ${pkgs.glibc}/lib ${pkgs.stdenv.cc.cc.lib}/lib; do
    for library in "$directory"/*.so*; do
      test ! -f "$library" || cp -L "$library" "$receiver/lib/$(basename "$library")"
    done
  done
  cp ${pkgs.stdenv.cc.bintools.dynamicLinker} "$receiver/lib64/ld-linux-x86-64.so.2"
  cp ${./portable-runtime.bl} "$receiver/tmp/control.bl"
  cp ${drop} "$receiver/bin/bl"
  chmod 755 "$receiver/bin/bl"
  printf 'root:x:0:0:root:/root:/bin/sh\n' > "$receiver/etc/passwd"
  printf 'root:x:0:\n' > "$receiver/etc/group"
  printf '127.0.0.1 localhost\n' > "$receiver/etc/hosts"
  printf 'hosts: files\n' > "$receiver/etc/nsswitch.conf"
  ${pkgs.util-linux}/bin/mount --bind /dev "$receiver/dev"
  ${pkgs.util-linux}/bin/mount -t proc proc "$receiver/proc"
  mkdir -p "$out"
  ${pkgs.coreutils}/bin/timeout 90 ${pkgs.coreutils}/bin/chroot "$receiver" \
    /bin/env -i HOME=/root PATH=/bin:/usr/bin LD_LIBRARY_PATH=/lib:/lib64 \
      ELIXIR_ERL_OPTIONS='+fnu +S 4:4 +SDcpu 2:2 +SDio 1:1' \
      /bin/bl --cold run /tmp/control.bl \
      > "$out/receiver.log" 2>&1
  grep -x 42 "$out/receiver.log"
  printf '{"passed":true,"nixStoreVisible":false,"answer":42,"nativeJson":true}\n' > "$out/result.json"
'')
