# An immutable, content-addressed startup capsule. Its identity comes from
# actual retained driver bytes and constructor receipts, not the SDK container.
# The worker still checks every input and native provenance before using it.
{ pkgs, directory }:
let
  source = builtins.path {
    path = builtins.toPath (builtins.unsafeDiscardStringContext directory);
    name = "beam-lisp-producer-inputs";
  };
in pkgs.runCommand "beam-lisp-producer" {
  nativeBuildInputs = [ pkgs.gnutar pkgs.gzip ];
} ''
  mkdir -p "$out"
  tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner \
    -czf "$out/producer.tar.gz" -C ${source} .
''
