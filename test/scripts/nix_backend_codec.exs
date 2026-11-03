sdk = System.fetch_env!("BL_CODEC_SDK")
for path <- Path.wildcard(sdk <> "/lib/*/ebin"),
    not String.starts_with?(Path.basename(Path.dirname(path)), "beam_lisp-"),
    do: Code.prepend_path(path)
Code.prepend_path(System.fetch_env!("BL_ROOT") <> "/ebin")
Application.load(:beam_lisp)
for app <- Application.spec(:beam_lisp, :applications) || [],
    do: ({:ok, _} = Application.ensure_all_started(app))
{:ok, _} = Application.ensure_all_started(:beam_lisp)
BeamLisp.AOT.boot()
BeamLisp.eval("""
(ns backend.codec-qualification (:require [build.backend :as backend]))
(doseq [name ["local" "configured" "nixbuild" "ssh"]]
  (backend/compile-file! (str "tooling/build-backends/" name ".bl")))
""")
File.mkdir_p!(System.fetch_env!("BL_CODEC_GENERATED"))
for name <- ["local", "configured", "nixbuild", "ssh"] do
  File.cp!("tooling/build-backends/#{name}.nix", Path.join(System.fetch_env!("BL_CODEC_GENERATED"), name <> ".nix"))
end
BeamLisp.Launcher.start_app!(["--cold", "test", "test/bl/nix_test.bl", "test/bl/build_backend_test.bl"], %{})
