# Dependency compilation runs on the committed compiler floor. Its tools are
# ordinary Source outside the source-free floor image; SDK/compiler edits are
# not dependency compiler inputs.
source = System.fetch_env!("BL_DEPENDENCY_SOURCE")
root = System.fetch_env!("BL_ROOT")
seed = source <> "/priv/bootstrap/seed"
File.mkdir_p!(root <> "/priv/bootstrap")
File.cp_r!(seed, root <> "/priv/bootstrap/seed")
File.cp_r!(seed, root <> "/ebin")
Code.prepend_path(root <> "/ebin")
{:ok, [floor]} = :file.consult(String.to_charlist(seed <> "/manifest.term"))
# A compiler-only sealed image has no library ownership rows. The bootstrap
# manifest remains the authority for every executable floor member.
File.write!(root <> "/priv/sdk-code.term", :erlang.term_to_binary(%{
  :"compiler-key" => floor["compiler_key"], version: 2, identities: :binary, modules: %{}
}, [:deterministic]))
File.mkdir_p!(root <> "/priv/native")
File.ln_s!(System.fetch_env!("BL_DEPENDENCY_NATIVE"), root <> "/priv/native/lazy_memo.so")
for app <- [:crypto, :public_key, :ssl, :inets, :logger],
    do: ({:ok, _} = Application.ensure_all_started(app))
Application.load(:beam_lisp)
BeamLisp.AOT.boot()
BeamLisp.Env.add_search_path(source <> "/priv/build")
:ok = BeamLisp.Loader.ensure_loaded("deps-compile")
compile = BeamLisp.Env.fetch!("deps-compile", "compile!")
result = BeamLisp.Ns.Rt.invoke(compile, [source, 60000, &IO.puts/1])
rows = BeamLisp.Ns.Rt.invoke(BeamLisp.Env.fetch!("core", "to-list"), [result.results])
IO.inspect(Enum.filter(rows, &(&1.state == :failed)), label: "DEPENDENCY FAILURES", limit: :infinity)
IO.puts("DEPENDENCIES packages=#{length(rows)} passes=#{result.passes} ok=#{result.ok?}")
unless result.ok?, do: raise("locked dependency compilation failed")
