# Keep the language's pinned solver version while making it executable in the
# Nix SDK. Portable packaging retargets these ELF files afterwards.
{ pkgs, archive }:
pkgs.runCommand "beam-lisp-z3-4.16.0" {
  nativeBuildInputs = [ pkgs.unzip pkgs.patchelf ];
} ''
  unzip -q ${archive} -d unpacked
  mkdir -p "$out/bin"
  cp unpacked/*/bin/z3 unpacked/*/bin/libz3.so "$out/bin/"
  cp unpacked/*/LICENSE.txt "$out/"
  chmod u+w "$out/bin/"*
  patchelf --set-interpreter ${pkgs.stdenv.cc.bintools.dynamicLinker} "$out/bin/z3"
  for binary in "$out/bin/"*; do
    patchelf --set-rpath "$out/bin:${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.glibc}/lib" "$binary"
  done
  "$out/bin/z3" --version | grep -F 'Z3 version 4.16.0'
  printf '(check-sat)\n' | "$out/bin/z3" -in | grep -x sat
''
