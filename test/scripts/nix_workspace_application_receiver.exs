# Consume compiled application units with the native selection installed by
# normal application-product/build!. No alternate NIF paths or project Source.
sdk = System.fetch_env!("BL_APPLICATION_SDK")
image = System.fetch_env!("BL_APPLICATION_IMAGE")
project = System.fetch_env!("BL_WORKSPACE_PROJECT")
true = File.cwd!() == project
false = File.exists?(Path.join(project, "src"))
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
(let [product (System/fetch_env! "BL_APPLICATION_PRODUCT")
      sdk (System/fetch_env! "BL_APPLICATION_SDK")
      root (System/fetch_env! "BL_WORKSPACE_PROJECT")
      descriptor (Jason/decode! (File/read! (Path/join product "artifact.json")))
      _ (BeamLisp.Loader/ensure_loaded "artifact")
      result ((BeamLisp.Env/fetch_exact! "artifact" "verify-application!") product sdk (get descriptor "source"))
      rows (get result "units")
      _ (assert (= ["artifact.workspace"] (mapv #(get % "namespace") rows)))
      library (Path/join product "native/workspace_demo.so")
      selected (Path/join root "priv/native/workspace_demo.so")
      _ (assert (= (File/read_link! library) (File/read_link! selected)))
      _ (assert (File/regular? selected))
      _ (assert (not (BeamLisp.Env/loaded_ns? "artifact.workspace")))
      directories (mapv #(Path/join product (get % "directory")) rows)
      verified (mapv #(BeamLisp.AOT/verify_unit %) directories)]
  (erlang/trace_pattern (tuple :Elixir.BeamLisp.AOT :compile_file 2) true (list :local :call_count))
  (doseq [directory directories] (Code/prepend_path directory))
  (doseq [unit verified]
    (BeamLisp.Env/publish_binaries! (:beams unit) "immutable-workspace-application-control"))
  (doseq [row rows]
    (let [namespace (get row "namespace") module (BeamLisp.Emit/module_for namespace)]
      (BeamLisp.AOT/init_loaded_module namespace module)
      (BeamLisp.Env/mark_emitted namespace module)))
  (assert (= 0 (elem (erlang/trace_info (tuple :Elixir.BeamLisp.AOT :compile_file 2) :call_count) 1)))
  (let [answer ((BeamLisp.Env/fetch_exact! "artifact.workspace" "answer"))
        message ((BeamLisp.Env/fetch_exact! "artifact.workspace" "support-message"))]
    (assert (= 42 answer))
    (assert (= "workspace support is captured" message))
    (println (Jason/encode! {"status" "passed" "answer" answer "supportMessage" message
                           "product" product "selectedLibrary" (File/read_link! selected)
                           "sourceAvailable" false "compileCalls" 0})))
  (println "IMMUTABLE-WORKSPACE-APPLICATION passed"))
""")
