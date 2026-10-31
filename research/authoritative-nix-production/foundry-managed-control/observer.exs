# Receiver control for test/fixtures/contextual-language/world.bl.
# Consume the verified paired unit without loading project Source providers.
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
for path <- ["operations", "support", "credentials"], do: BeamLisp.Env.add_search_path(Path.join("/home/othman/code/undefine/foundry/src/foundry", path))
BeamLisp.run_file(Path.join(System.fetch_env!("BL_FOUNDRY_LEDGER_CONTROL"), "observer.bl"))
