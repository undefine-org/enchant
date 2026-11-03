# Exercise current client Source in a private compiler world.
sdk = System.fetch_env!("BL_POLICY_SDK")
for path <- Path.wildcard(sdk <> "/lib/*/ebin"),
    not String.starts_with?(Path.basename(Path.dirname(path)), "beam_lisp-"),
    do: Code.prepend_path(path)
Code.prepend_path(System.fetch_env!("BL_ROOT") <> "/ebin")
Application.load(:beam_lisp)
for app <- Application.spec(:beam_lisp, :applications) || [],
    do: ({:ok, _} = Application.ensure_all_started(app))
BeamLisp.AOT.boot()
for namespace <- ["artifact-process", "artifact-jobs", "artifact"],
    do: (:ok = BeamLisp.Loader.ensure_loaded(namespace))

settings = %{"NIX_CONFIG" => "include /operator/nix-$literal.conf\nmax-jobs = 0\n",
             "NIX_SSHOPTS" => "-F/operator/ssh config", "SSH_AUTH_SOCK" => "/operator/agent"}
before = Map.new(Map.keys(settings) ++ ["UNRELATED_SECRET", "NIX_CONF_DIR"], &{&1, System.get_env(&1)})
try do
  System.put_env(settings)
  System.put_env("UNRELATED_SECRET", "must-stay-out")
  System.delete_env("NIX_CONF_DIR")
  actual = BeamLisp.eval("(artifact-process/operator-environment)")
  ^settings = Map.take(actual, Map.keys(settings))
  false = Map.has_key?(actual, "UNRELATED_SECRET")
  false = Map.has_key?(actual, "NIX_CONF_DIR")
  # The real env-i process adapter forwards exactly this operator environment.
  result = BeamLisp.eval("(artifact-process/run \"/usr/bin/env\" [] {:env (artifact-process/operator-environment) :timeout-ms 5000})")
  :exited = result[:status]
  0 = result[:exit]
  output = result[:out]
  true = String.contains?(output, "NIX_CONFIG=" <> settings["NIX_CONFIG"])
  true = String.contains?(output, "NIX_SSHOPTS=" <> settings["NIX_SSHOPTS"])
  false = String.contains?(output, "UNRELATED_SECRET")
  IO.puts(~s({"status":"passed","checks":8,"current_source_clients":3}))
after
  for {name, value} <- before do
    if value, do: System.put_env(name, value), else: System.delete_env(name)
  end
end
