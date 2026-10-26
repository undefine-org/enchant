# Evaluate routing only; main owns all realization and deployment checks.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgsSource = builtins.fetchTree lock.nodes.nixpkgs.locked;
  evaluated = import (pkgsSource.outPath + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nix/workstation-artifacts.nix {
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
assert station.hostName == "100.66.112.86";
assert station.protocol == "ssh-ng";
assert station.sshUser == "nix-ssh";
assert station.sshKey == "/var/lib/beam-workstation/keys/build_ed25519";
assert station.maxJobs == 2;
assert cfg.programs.ssh.knownHosts.beam-artifact-station.hostNames == [ station.hostName ];
assert builtins.elem "kvm" station.supportedFeatures;
assert builtins.all (entry: entry.assertion) cfg.assertions;
{
  status = "passed";
  localJobs = cfg.nix.settings.max-jobs;
  inherit (station) hostName protocol systems maxJobs;
  keyIsHostPath = !(builtins.substring 0 11 station.sshKey == "/nix/store/");
}
