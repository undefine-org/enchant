# The same Source-owned policy configures a NixOS host and a clean CI client.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgsSource = builtins.fetchTree lock.nodes.nixpkgs.locked;
  evaluate = name: (import (pkgsSource.outPath + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ (import ../../nix/backend-description.nix {
      description = ../../tooling/build-backends + "/${name}.bl";
    }) {
      system.stateVersion = "25.05";
      boot.isContainer = true;
      fileSystems."/" = { device = "none"; fsType = "tmpfs"; };
    } ];
  }).config;
  local = evaluate "local";
  cloud = evaluate "nixbuild";
  ssh = evaluate "ssh";
  builder = builtins.head cloud.nix.buildMachines;
in
assert local.nix.settings.max-jobs == 1;
assert cloud.nix.settings.max-jobs == 0;
assert cloud.nix.distributedBuilds;
assert builder.hostName == "eu.nixbuild.net" && builder.protocol == "ssh";
assert builder.maxJobs == 4 && builder.systems == [ "x86_64-linux" ];
assert builtins.elem "kvm" builder.supportedFeatures;
assert (builtins.head ssh.nix.buildMachines).sshKey == "/run/keys/local-build";
assert builtins.all (cfg: builtins.all (row: row.assertion) cfg.assertions) [ local cloud ssh ];
{ status = "passed"; sourceOwned = true; cases = [ "local" "nixbuild" "ssh" ]; }
