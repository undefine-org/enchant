# Build-free module contract check. No host activation or daemon changes.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  source = builtins.fetchTree lock.nodes.nixpkgs.locked;
  evaluated = import (source.outPath + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nix/artifact-host.nix {
      services.beam-lisp-artifacts.enable = true;
      system.stateVersion = "25.05";
    } ];
  };
  cfg = evaluated.config;
in
assert cfg.nix.settings.sandbox;
assert !cfg.nix.settings.sandbox-fallback;
assert cfg.nix.settings.use-cgroups;
assert cfg.nix.settings.max-jobs == 1;
assert cfg.systemd.services.nix-daemon.serviceConfig.MemoryMax == "8G";
assert cfg.systemd.services.nix-daemon.serviceConfig.MemorySwapMax == "1G";
assert cfg.systemd.services.nix-daemon.serviceConfig.Delegate;
assert cfg.environment.sessionVariables.BL_NATIVE_PROVIDER == "nix";
{
  status = "passed";
  sandbox = cfg.nix.settings.sandbox;
  cgroups = cfg.nix.settings.use-cgroups;
  jobs = cfg.nix.settings.max-jobs;
  platform = cfg.environment.sessionVariables.BL_ARTIFACT_PLATFORM;
  provider = cfg.environment.sessionVariables.BL_NATIVE_PROVIDER;
}
