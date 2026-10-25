# Opt-in managed Linux build-host policy. Apply through the host's normal NixOS deployment.
{ config, lib, pkgs, ... }:
let cfg = config.services.beam-lisp-artifacts;
in {
  options.services.beam-lisp-artifacts = {
    enable = lib.mkEnableOption "managed Beam Lisp native artifact production";
    platform = lib.mkOption {
      type = lib.types.package;
      default = import ./artifact-platform.nix { inherit pkgs; };
      description = "Trusted immutable recipe and lock platform used by Beam Lisp clients.";
    };
    maxJobs = lib.mkOption { type = lib.types.ints.positive; default = 1; description = "Concurrent local Nix builds on this shared host."; };
    daemonMemoryMax = lib.mkOption { type = lib.types.str; default = "8G"; description = "Aggregate Nix daemon and worker cgroup memory limit."; };
    daemonMemorySwapMax = lib.mkOption { type = lib.types.str; default = "1G"; description = "Aggregate Nix daemon and worker cgroup swap limit."; };
  };
  config = lib.mkIf cfg.enable {
    nix.settings = {
      sandbox = true;
      sandbox-fallback = false;
      use-cgroups = true;
      max-jobs = cfg.maxJobs;
    };
    systemd.services.nix-daemon.serviceConfig = {
      Delegate = true;
      MemoryMax = cfg.daemonMemoryMax;
      MemorySwapMax = cfg.daemonMemorySwapMax;
    };
    environment.sessionVariables.BL_ARTIFACT_PLATFORM = toString cfg.platform;
    environment.sessionVariables.BL_NATIVE_PROVIDER = "nix";
  };
}
