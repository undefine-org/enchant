# Managed Linux artifact policy. Apply once through the host deployment.
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
    buildStation = lib.mkOption {
      default = null;
      description = "Remote build station for this client; commands require no routing flags.";
      type = lib.types.nullOr (lib.types.submodule {
        options = {
          evaluation = lib.mkOption {
            default = null;
            description = "Optional station evaluation transport from the local host description. ssh-ng alone only places realization.";
            type = lib.types.nullOr (lib.types.submodule {
              options = {
                storeUri = lib.mkOption { type = lib.types.str; };
                transport = lib.mkOption {
                  type = lib.types.listOf lib.types.str;
                  description = "Operator-owned argv, with one {endpoint} token for the copied immutable station executable.";
                };
              };
            });
          };
          hostName = lib.mkOption { type = lib.types.str; };
          sshUser = lib.mkOption { type = lib.types.str; default = "nix-ssh"; };
          sshKey = lib.mkOption {
            type = lib.types.str;
            description = "Absolute host-owned key location. Key bytes must never enter the Nix store.";
          };
          hostPublicKey = lib.mkOption {
            type = lib.types.nullOr lib.types.str;
            default = null;
            description = "Pinned SSH host public key, or null when managed by another host module.";
          };
          systems = lib.mkOption { type = lib.types.listOf lib.types.str; default = [ "x86_64-linux" ]; };
          maxJobs = lib.mkOption { type = lib.types.ints.positive; default = 2; };
          supportedFeatures = lib.mkOption {
            type = lib.types.listOf lib.types.str;
            default = [ "kvm" "nixos-test" "benchmark" ];
          };
        };
      });
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
      max-jobs = if cfg.buildStation == null then cfg.maxJobs else 0;
      builders-use-substitutes = true;
    };
    assertions = lib.optionals (cfg.buildStation != null) [{
      assertion = lib.hasPrefix "/" cfg.buildStation.sshKey
        && !(lib.hasPrefix "/nix/store/" cfg.buildStation.sshKey);
      message = "Artifact build-station credentials require an absolute host key path outside the Nix store.";
    }];
    nix.distributedBuilds = lib.mkIf (cfg.buildStation != null) true;
    nix.buildMachines = lib.optional (cfg.buildStation != null) {
      inherit (cfg.buildStation) hostName sshUser sshKey systems maxJobs supportedFeatures;
      protocol = "ssh-ng";
    };
    programs.ssh.knownHosts = lib.mkIf
      (cfg.buildStation != null && cfg.buildStation.hostPublicKey != null) {
        beam-artifact-station = {
          hostNames = [ cfg.buildStation.hostName ];
          publicKey = cfg.buildStation.hostPublicKey;
        };
      };
    systemd.services.nix-daemon.serviceConfig = {
      Delegate = true;
      MemoryMax = cfg.daemonMemoryMax;
      MemorySwapMax = cfg.daemonMemorySwapMax;
    };
    environment.etc = lib.mkIf (cfg.buildStation != null && cfg.buildStation.evaluation != null) {
      "beam-lisp/build-station.json".text = builtins.toJSON {
        version = 1;
        inherit (cfg.buildStation.evaluation) storeUri transport;
      };
    };
    environment.sessionVariables.BL_ARTIFACT_PLATFORM = toString cfg.platform;
    environment.sessionVariables.BL_NATIVE_PROVIDER = "nix";
  };
}
