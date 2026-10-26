# Receiver control for test/fixtures/artifact-production. Production verifies
# ordinary application units; this never grants them SDK authority.
sdk = System.fetch_env!("BL_APPLICATION_SDK")
image = System.get_env("BL_APPLICATION_IMAGE") || Path.join(sdk, "image")
for path <- Path.wildcard(Path.join(sdk, "lib/*/ebin")),
    not String.starts_with?(Path.basename(Path.dirname(path)), "beam_lisp-"),
    do: Code.prepend_path(path)
Code.prepend_path(Path.join(image, "ebin"))
if System.get_env("BL_REQUIRE_SOURCE_FREE") == "1" do
  [] = Path.wildcard(Path.join(image, "**/*.bl"))
end
Application.load(:beam_lisp)
for app <- Application.spec(:beam_lisp, :applications) || [], do: {:ok, _} = Application.ensure_all_started(app)
:ok = BeamLisp.LazyMemo.ensure_loaded!()
BeamLisp.AOT.boot()
BeamLisp.eval("""
(let [product (System/fetch_env! "BL_APPLICATION_PRODUCT")
      result (Jason/decode! (File/read! (str product "/result.json")))
      directories (Enum/map (get result "units") #(Path/join product (get % "directory")))
      verified (Enum/map directories #(BeamLisp.AOT/verify_unit %))]
  (doseq [directory directories] (Code/prepend_path directory))
  (doseq [unit verified] (BeamLisp.Env/publish_binaries! (:beams unit) "immutable-application-control"))
  (doseq [row (get result "units")]
    (let [namespace (get row "namespace") module (BeamLisp.Emit/module_for namespace)]
      (BeamLisp.AOT/init_loaded_module namespace module)
      (BeamLisp.Env/mark_emitted namespace module)))
  (let [namespace "artifact.demo.consumer"
        invoke (fn [name args] (BeamLisp.Ns.Rt/invoke (BeamLisp.Env/fetch_exact! namespace name) args))
        answer (invoke "answer" (list))
        value (invoke "value" (list))
        closure (invoke "adder" (list 10))
        closed (BeamLisp.Ns.Rt/invoke closure (list 32))
        initialized (BeamLisp.Loader.Server/run #(Process/get :artifact-demo-initialized))]
    (assert (= (String/to_integer (or (System/get_env "BL_APPLICATION_EXPECT_ANSWER") "42")) answer))
    (when-let [expected (System/get_env "BL_APPLICATION_EXPECT_BASE")]
      (assert (= (String/to_integer expected) (BeamLisp.Env/fetch! "artifact.demo.values" "base")))) (assert (= 3 value)) (assert (= 42 closed)) (assert (= 1 initialized))
    (BeamLisp.AOT/init_loaded_module namespace (BeamLisp.Emit/module_for namespace))
    (assert (= 1 (BeamLisp.Loader.Server/run #(Process/get :artifact-demo-initialized))))
    (println (str "IMMUTABLE-MULTI answer=" answer " value=" value " closure=" closed " initializer=" initialized))))
""")

