let
 root = /home/othman/code/undefine/beam-lisp--execution-protocol;
 pkgs = import /nix/store/rhsxvv1380jmchb5p3a43d24mhlmp2ry-source { system = "x86_64-linux"; };
 previous = builtins.storePath "/nix/store/0a57h5b63la8wgxl01cgpcggx1v4sx4c-beam-lisp-checkout-platform";
 recipes = import (root + "/nix/artifact-platform.nix") { inherit pkgs; };
 platform = pkgs.runCommand "beam-lisp-coordinator-platform-control" {} ''
   mkdir -p "$out"
   ln -s ${previous}/bin "$out/bin"
   ln -s ${previous}/native-products "$out/native-products"
   ln -s ${recipes} "$out/artifact-platform"
 '';
 in import (root + "/nix/coordinator-runtime.nix") {
 inherit pkgs platform;
 source = builtins.storePath "/nix/store/lcjwbb7nvbq3d3nh2h24dq4ksljl6439-beam-lisp-engine-snapshot";
 compiler = builtins.storePath "/nix/store/v90rw0bfhxcq9xba767cpha9gv7ivhxj-beam-lisp-compiler-1";
 dependencies = builtins.storePath "/nix/store/s93zhbh08y2ar2w6ynd6k1hzm4lf1ysm-beam-lisp-dependencies-1";
 }
