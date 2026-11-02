# Evaluate routing only; main owns all realization and deployment checks.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgsSource = builtins.fetchTree lock.nodes.nixpkgs.locked;
  evaluated = import (pkgsSource.outPath + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ (import ../../nix/workstation-artifacts.nix { station = {
      hostName = "build.example.invalid";
      sshUser = "builder";
      sshKey = "/run/keys/local-build";
      maxJobs = 3;
      evaluation = {
        storeUri = "ssh-ng://fixture-store";
        transport = [ "ssh" "fixture-operator" "{endpoint}" ];
      };
      hostPublicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMcF6me4e++om0gZLNkZ1H8LnB3r7VHJtqVdUQhLcF0z fixture";
    }; }) {
      system.stateVersion = "25.05";
      boot.isContainer = true;
      fileSystems."/" = { device = "none"; fsType = "tmpfs"; };
    } ];
  };
  cfg = evaluated.config;
  station = builtins.head cfg.nix.buildMachines;
in
assert (builtins.fromJSON cfg.environment.etc."beam-lisp/build-station.json".text) == {
  version = 1; storeUri = "ssh-ng://fixture-store";
  transport = [ "ssh" "fixture-operator" "{endpoint}" ];
};
assert cfg.nix.distributedBuilds;
assert cfg.nix.settings.max-jobs == 0;
assert cfg.nix.settings.builders-use-substitutes;
assert builtins.length cfg.nix.buildMachines == 1;
assert station.hostName == "build.example.invalid";
assert station.protocol == "ssh-ng";
assert station.sshUser == "builder";
assert station.sshKey == "/run/keys/local-build";
assert station.maxJobs == 3;
assert cfg.programs.ssh.knownHosts.beam-artifact-station.hostNames == [ station.hostName ];
assert builtins.elem "kvm" station.supportedFeatures;
assert builtins.all (entry: entry.assertion) cfg.assertions;
{
  status = "passed";
  localJobs = cfg.nix.settings.max-jobs;
  inherit (station) hostName protocol systems maxJobs;
  keyIsHostPath = !(builtins.substring 0 11 station.sshKey == "/nix/store/");
}
