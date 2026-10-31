# This workstation's routing policy. Import through its managed host deployment.
# Only the daemon reads the private key; this module contains its location.
{ ... }: {
  imports = [ ./artifact-host.nix ];
  services.beam-lisp-artifacts = {
    enable = true;
    buildStation = {
      hostName = "100.66.112.86";
      sshUser = "nix-ssh";
      hostPublicKey = builtins.replaceStrings [ "\n" ] [ "" ] (builtins.readFile ./build-station-host.pub);
      sshKey = "/var/lib/beam-workstation/keys/build_ed25519";
      systems = [ "x86_64-linux" ];
      maxJobs = 2;
      supportedFeatures = [ "kvm" "nixos-test" "benchmark" ];
    };
  };
}
