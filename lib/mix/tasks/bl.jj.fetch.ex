defmodule Mix.Tasks.Bl.Jj.Fetch do
  @moduledoc """
  Fetch the pinned, bundled jj into `priv/jj/`.

  jj is the change engine behind `bl vcs` (docs/jj-in-front-datom-in-the-back.md),
  and it is resolved at exactly one place — `priv/jj/bin/jj` — for the same reason
  z3 is: inside a drop, the first `bl`-adjacent binary on PATH may be a release
  script, and a dev loop must not depend on what a developer happens to have
  installed. `vcs.jj/bin` reads that path first; `VCS_JJ` overrides it (a test, a
  spike); PATH is the last resort.

  Vendored as a PINNED PREBUILT BINARY, never as a cargo dependency: jj's storage
  seams are compile-time factories and its library API is explicitly unstable, so
  the contract we depend on is its command line plus templates — which this task
  and the probe's measurements can both be tested against.

  The fetched tree is gitignored: it is a derived artifact, reproducible by
  re-running this task. Anything that packs a drop must run it first, or the
  payload ships without jj. Re-pinning means bumping `@version` and the digests
  in `@assets` (GitHub prints them per asset as `digest: sha256:…`).

      mix bl.jj.fetch
  """

  @shortdoc "Fetch the pinned jj binary into priv/jj/"

  use Mix.Task

  @version "0.45.1"
  @base "https://github.com/jj-vcs/jj/releases/download/v#{@version}"

  # {os, arch} => {asset basename, sha256 of the artifact}
  @assets %{
    {:linux, :x64} =>
      {"jj-v0.45.1-x86_64-unknown-linux-musl.tar.gz",
       "f35438350b5d61963aac5dd74ede510b31d6b9690769d1a6268cf058cc825f72"},
    {:linux, :arm64} =>
      {"jj-v0.45.1-aarch64-unknown-linux-musl.tar.gz",
       "7349a43dd5a20dbc998b10114daa0ee63d2ab863fb822c7eb6b0ebca5903cc69"},
    {:macos, :x64} =>
      {"jj-v0.45.1-x86_64-apple-darwin.tar.gz",
       "6171582d0b5a98a1005cd9643faebff7936812ec264d7968a39d9cef3654a99b"},
    {:macos, :arm64} =>
      {"jj-v0.45.1-aarch64-apple-darwin.tar.gz",
       "51ba42e3d0682616f6eb015045bfe45289b396f03511f9897f645ce8e9272743"},
    {:windows, :x64} =>
      {"jj-v0.45.1-x86_64-pc-windows-msvc.zip",
       "5dbf2619272c897394d34190a94b21a6ab8d1e8e59fcf7dfc173d8fa8aa90bf0"},
    {:windows, :arm64} =>
      {"jj-v0.45.1-aarch64-pc-windows-msvc.zip",
       "0f869d108316149f211d2ba50a626b4fe8ef99232db52f13300bde106821be9e"}
  }

  # The archive ships exactly three files. Keep the binary and the licence; the
  # README is upstream's, and a vendored artifact should carry as little of
  # upstream's prose as it can.
  @keep ["jj", "jj.exe", "LICENSE"]

  @impl true
  def run(_argv) do
    {asset, sha256} = asset_for(platform())
    url = "#{@base}/#{asset}"
    dest = Path.join(to_string(:code.priv_dir(:beam_lisp)), "jj")

    Mix.shell().info("fetching #{url}")
    body = download(url)

    actual = :crypto.hash(:sha256, body) |> Base.encode16(case: :lower)

    if actual != sha256 do
      Mix.raise("sha256 mismatch for #{asset}\n  pinned:  #{sha256}\n  actual:  #{actual}")
    end

    Mix.shell().info("sha256 verified; extracting to #{dest}")
    File.rm_rf!(dest)
    File.mkdir_p!(dest)
    extract(body, dest, asset)
    prune(dest)

    exe = Path.join([dest, "bin", exe_name()])
    File.chmod!(exe, 0o755)

    {out, 0} = System.cmd(exe, ["--version"])
    version = String.trim(out)

    if not String.contains?(version, @version) do
      Mix.raise("the fetched jj does not name #{@version}: #{version}")
    end

    Mix.shell().info("bundled jj ready: #{version}")
  end

  defp platform do
    sys = :erlang.system_info(:system_architecture) |> to_string()

    arch =
      cond do
        String.starts_with?(sys, "x86_64") or String.starts_with?(sys, "amd64") -> :x64
        String.starts_with?(sys, "aarch64") or String.starts_with?(sys, "arm64") -> :arm64
        true -> Mix.raise("unsupported CPU architecture: #{sys}")
      end

    os =
      case :os.type() do
        {:unix, :darwin} -> :macos
        {:unix, :linux} -> :linux
        {:win32, _} -> :windows
        other -> Mix.raise("unsupported OS: #{inspect(other)}")
      end

    {os, arch}
  end

  defp asset_for(key) do
    @assets[key] || Mix.raise("no pinned jj asset for #{inspect(key)} (jj #{@version})")
  end

  defp download(url) do
    {:ok, _} = Application.ensure_all_started(:inets)
    {:ok, _} = Application.ensure_all_started(:ssl)

    ssl = [
      verify: :verify_peer,
      cacerts: :public_key.cacerts_get(),
      depth: 3,
      customize_hostname_check: [
        match_fun: :public_key.pkix_verify_hostname_match_fun(:https)
      ]
    ]

    case :httpc.request(:get, {String.to_charlist(url), []}, [ssl: ssl], body_format: :binary) do
      {:ok, {{_, code, _}, _headers, body}} when code in 200..299 and is_binary(body) ->
        body

      {:ok, {{_, code, _}, _headers, _body}} ->
        Mix.raise("download failed: HTTP #{code} from #{url}")

      {:error, reason} ->
        Mix.raise("download failed: #{inspect(reason)} from #{url}")
    end
  end

  # Both archives hold their files at the top level — no wrapper directory, so
  # the extraction lands where `vcs.jj/bin` looks for it: `bin/jj`.
  defp extract(body, dest, asset) do
    bin = Path.join(dest, "bin")
    File.mkdir_p!(bin)

    case Path.extname(asset) do
      ".zip" ->
        {:ok, _} = :zip.extract(body, cwd: String.to_charlist(dest))

      _ ->
        :ok = :erl_tar.extract({:binary, body}, [:compressed, {:cwd, String.to_charlist(dest)}])
    end

    # `bin/jj.exe` on windows, but keep one shape for callers: bin/<name>
    case File.ls!(dest) do
      entries ->
        for entry <- entries, entry in ["jj", "jj.exe"] do
          File.rename!(Path.join(dest, entry), Path.join(bin, entry))
        end
    end
  end

  defp prune(dest) do
    dest
    |> Path.join("**/*")
    |> Path.wildcard()
    |> Enum.reject(fn p -> File.dir?(p) or Path.basename(p) in @keep end)
    |> Enum.each(&File.rm_rf!/1)

    dest
    |> Path.join("**/*")
    |> Path.wildcard()
    |> Enum.filter(&File.dir?/1)
    |> Enum.sort_by(&String.length/1, :desc)
    |> Enum.each(fn d -> if File.ls!(d) == [], do: File.rmdir!(d) end)
  end

  defp exe_name do
    case :os.type() do
      {:win32, _} -> "jj.exe"
      _ -> "jj"
    end
  end
end
