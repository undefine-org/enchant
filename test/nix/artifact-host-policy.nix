# Deployment-independent routing: local, externally configured, and SSH service.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgsSource = builtins.fetchTree lock.nodes.nixpkgs.locked;
  evaluate = settings: extra: (import (pkgsSource.outPath + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nix/artifact-host.nix {
      services.beam-lisp-artifacts = { enable = true; } // settings;
      system.stateVersion = "25.05";
      boot.isContainer = true;
      fileSystems."/" = { device = "none"; fsType = "tmpfs"; };
    } extra ];
  }).config;
  local = evaluate {} {};
  external = evaluate { maxJobs = 0; } {
    nix.distributedBuilds = true;
    nix.buildMachines = [{ hostName = "configured.example.invalid"; systems = [ "x86_64-linux" ]; }];
  };
  service = evaluate { buildStation = {
    hostName = "service.example.invalid";
    protocol = "ssh";
    maxJobs = 100;
    supportedFeatures = [ "kvm" "nixos-test" ];
  }; } {};
  machine = builtins.head service.nix.buildMachines;
  unspecified = evaluate { buildStation.hostName = "minimal.example.invalid"; } {};
  invalid = evaluate { buildStation = { hostName = "invalid.example.invalid"; sshKey = "/nix/store/forbidden-key"; }; } {};
in
assert local.nix.settings.max-jobs == 1;
assert local.nix.buildMachines == [];
assert external.nix.settings.max-jobs == 0;
assert (builtins.head external.nix.buildMachines).hostName == "configured.example.invalid";
assert service.nix.settings.max-jobs == 0;
assert machine.protocol == "ssh" && machine.sshUser == null && machine.sshKey == null;
assert machine.supportedFeatures == [ "kvm" "nixos-test" ] && machine.maxJobs == 100;
assert !(service.environment.etc ? "beam-lisp/build-station.json");
assert (builtins.head unspecified.nix.buildMachines).supportedFeatures == [];
assert builtins.all (cfg: builtins.all (entry: entry.assertion) cfg.assertions) [ local external service ];
assert builtins.any (entry: !entry.assertion) invalid.assertions;
{ status = "passed"; cases = [ "local" "external-routing" "ssh-service" "explicit-capabilities" "credential-boundary" ]; }
