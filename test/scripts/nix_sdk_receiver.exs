# Consume an actual produced SDK; the coordinator supplies a private image copy.
sdk = System.fetch_env!("BL_APPLICATION_SDK")
image = System.fetch_env!("BL_APPLICATION_IMAGE")
for suffix <- ["*.bl", "*.bl.md", "*.bl.org", "*.clj", "*.cljc", "*.ex", "*.exs"] do
  [] = Path.wildcard(Path.join(image, "**/" <> suffix))
end
for path <- Path.wildcard(Path.join(sdk, "lib/*/ebin")),
    not String.starts_with?(Path.basename(Path.dirname(path)), "beam_lisp-"),
    do: Code.prepend_path(path)
Code.prepend_path(Path.join(image, "ebin"))
Application.load(:beam_lisp)
for app <- Application.spec(:beam_lisp, :applications) || [], do: {:ok, _} = Application.ensure_all_started(app)
:ok = BeamLisp.LazyMemo.ensure_loaded!()
BeamLisp.AOT.boot()
BeamLisp.eval("""
(let [mode (System/fetch_env! "BL_SDK_RECEIVER_MODE") namespace "bl.json"]
  (assert (not (BeamLisp.Env/loaded_ns? namespace)))
  (when (= mode "missing")
    (let [path (Path/join (BeamLisp.Tiers/priv_root) "sdk-code.term")
          inventory (erlang/binary_to_term (File/read! path) (list :safe))]
      (File/write! path (erlang/term_to_binary
        (update inventory :modules dissoc "Elixir.BeamLisp.Ns.Bl.Json")))))
  (if (= mode "positive")
    (do
      (erlang/trace_pattern (tuple :Elixir.BeamLisp.AOT :compile_file 2) true (list :local :call_count))
      (BeamLisp.Loader/ensure_loaded namespace)
      (assert (BeamLisp.AOT/sdk_unit_compiled? namespace))
      (assert (= [20 22] (BeamLisp.Ns.Rt/invoke (BeamLisp.Env/fetch! namespace "decode") (list "[20,22]"))))
      (assert (= 0 (elem (erlang/trace_info (tuple :Elixir.BeamLisp.AOT :compile_file 2) :call_count) 1)))
      (BeamLisp.Loader/ensure_loaded "proc.owner-registry")
      (let [module (BeamLisp.Env/fetch! "proc.owner-registry" "registry")
            proof (BeamLisp.Env/prepare_sdk_class! module)]
        (assert (= module (:module proof))) (assert (:image? proof)))
      (assert (= 42 (BeamLisp/eval "(ns portable.fresh-project) (when true (+ 20 22))")))
      (assert (= 42 (BeamLisp/eval "(java.lang.Math/max 20 42)")))
      (assert (= 3 (BeamLisp/eval "(.length \\"abc\\")")))
      (assert (= 0 (elem (erlang/trace_info (tuple :Elixir.BeamLisp.AOT :compile_file 2) :call_count) 1))))
    (let [reason (try (BeamLisp.Loader/ensure_loaded namespace) :unexpected
                  (catch error (:original error)))]
      (println "SDK-REFUSAL" (pr-str reason))
      (assert (= (if (= mode "missing") (tuple :sdk_image_unit_missing namespace)
                    :sdk_image_preload_artifact_changed) reason))
      (assert (not (BeamLisp.Env/loaded_ns? namespace))))))
(println "SDK-RECEIVER passed")
""")
