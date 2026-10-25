let
  locked = builtins.getFlake ("git+file://" + toString ../..);
  pkgs = import locked.inputs.nixpkgs.outPath { system = "x86_64-linux"; };
  platform = import ../../nix/prepare-checkout.nix {};
  bounded = import ../../nix/bounded-build.nix {
    inherit pkgs;
    memoryMiB = 512;
    diskMiB = 1024;
  };
in bounded (pkgs.runCommand "beam-lisp-checkout-prerequisites-control" {
  nativeBuildInputs = [ pkgs.python3 ];
} ''
  export BL_TEST_CHECKOUT_PLATFORM=${platform}
  mkdir -p "$out"
  python3 ${../scripts/test_checkout_prerequisites.py} > "$out/controls.log" 2>&1 || {
    cat "$out/controls.log"
    exit 1
  }
  cat "$out/controls.log"
'')
