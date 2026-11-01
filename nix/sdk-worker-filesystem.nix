# One immutable local filesystem per SDK, shared by independent build guests.
# Guest reads use a read-only block device rather than shared-store file RPCs.
{ pkgs, sdk }:
pkgs.runCommand "beam-lisp-worker-sdk" {
  nativeBuildInputs = [ pkgs.e2fsprogs ];
} ''
  mkdir -p "$out"
  sdk_kib=$(du --apparent-size -sk ${sdk}/lib/ | cut -f1)
  truncate -s "$(( (sdk_kib + sdk_kib / 4 + 65536) * 1024 ))" "$out/lib.ext4"
  E2FSPROGS_FAKE_TIME=1 mkfs.ext4 -q -F -U 11111111-1111-4111-8111-111111111111 \
    -O ^has_journal -E lazy_itable_init=0,root_owner=0:0 \
    -d ${sdk}/lib/ "$out/lib.ext4"
''
