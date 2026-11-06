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
(doseq [path (Path/wildcard "tooling/build-backends/*.bl")] (backend/compile-file! path))
""")
File.mkdir_p!(System.fetch_env!("BL_CODEC_GENERATED"))
for path <- Path.wildcard("tooling/build-backends/*.nix") do
  File.cp!(path, Path.join(System.fetch_env!("BL_CODEC_GENERATED"), Path.basename(path)))
end
BeamLisp.Launcher.start_app!(["--cold", "test", "test/bl/nix_test.bl", "test/bl/build_backend_test.bl"], %{})
