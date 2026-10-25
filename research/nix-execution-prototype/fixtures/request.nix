{ requestJson, token ? "stable" }:
let request = builtins.fromJSON requestJson;
in assert builtins.attrNames request == [ "answer" ];
import ./artifact.nix { inherit (request) answer; inherit token; }
