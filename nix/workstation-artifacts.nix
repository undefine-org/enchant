# Routing is supplied by the operator's local build description. Beam Lisp
# supplies the interface, never a machine address, credential or capacity.
{ station }:
{ ... }: {
  imports = [ ./artifact-host.nix ];
  services.beam-lisp-artifacts = {
    enable = true;
    buildStation = station;
  };
}
