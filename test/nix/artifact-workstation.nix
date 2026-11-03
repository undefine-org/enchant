# Evaluate routing only; main owns all realization and deployment checks.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgsSource = builtins.fetchTree lock.nodes.nixpkgs.locked;
  evaluated = import (pkgsSource.outPath + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ (import ../../nix/workstation-artifacts.nix {
      description = ../../tooling/build-backends/ssh.bl;
    }) {
      system.stateVersion = "25.05";
      boot.isContainer = true;
      fileSystems."/" = { device = "none"; fsType = "tmpfs"; };
    } ];
  };
  cfg = evaluated.config;
  station = builtins.head cfg.nix.buildMachines;
in
assert cfg.nix.distributedBuilds;
assert cfg.nix.settings.max-jobs == 0;
assert cfg.nix.settings.builders-use-substitutes;
assert builtins.length cfg.nix.buildMachines == 1;
assert station.hostName == "build.example.invalid";
assert station.protocol == "ssh-ng";
assert station.sshUser == "builder";
assert station.sshKey == "/run/keys/local-build";
assert station.maxJobs == 2;
assert builtins.elem "kvm" station.supportedFeatures;
assert builtins.all (entry: entry.assertion) cfg.assertions;
{
  status = "passed";
  localJobs = cfg.nix.settings.max-jobs;
  inherit (station) hostName protocol systems maxJobs;
  keyIsHostPath = !(builtins.substring 0 11 station.sshKey == "/nix/store/");
}
