defmodule BeamLisp.DaemonVcsTest do
  @moduledoc """
  Automatic version control under the daemon: what a command DID becomes a
  change in the tree's jj repository.

  This is the half of `bl vcs` that cannot be tested from beam-lisp alone — the
  beam-lisp suite drives `vcs` directly, and proves the mirror, the queue and
  the gate; here the question is the *seam*: a request arrives over the socket,
  the executor runs it in the daemon's VM, and `bl.cli/run-argv` records the
  result on its way out. Only a real daemon and a real socket exercise that.

  The two facts that matter, and the reasons they are the ones asserted:

    * a command that changed the tree IS recorded — with the command line as
      the description, because "why" is the question history has to answer;
    * a command that changed NOTHING is not recorded — otherwise a history is a
      log of what you typed, not of what happened, and it stops being readable.

  jj is the pinned binary (`mix bl.jj.fetch` → `priv/jj/bin/jj`). Without it
  there is no recording at all, so the suite skips rather than failing: an
  absent optional is a fact about the host, not a defect in the code.
  """

  use ExUnit.Case, async: false

  alias BeamLisp.Daemon.{Protocol, Paths, Server}


  setup do
    root = File.cwd!()

    case Process.whereis(Server) do
      nil ->
        :ok

      old ->
        try do
          GenServer.stop(old, :normal, 2_000)
        catch
          :exit, _ -> :ok
        end
    end

    {:ok, pid} = Server.start_link(root: root, boot: true, idle_seconds: 0)
    {:ok, ep} = Paths.endpoints(root)
    wait_for(fn -> File.exists?(ep.token) end)

    on_exit(fn ->
      if Process.alive?(pid) do
        try do
          GenServer.stop(pid, :normal, 2_000)
        catch
          :exit, _ -> :ok
        end
      end
    end)

    jj = jj_bin()

    if File.exists?(jj) do
      {:ok, root: root, ep: ep, token: File.read!(ep.token), tree: Paths.tree_fingerprint(root), jj: jj}
    else
      {:skip, "no pinned jj (#{jj}) — run `mix bl.jj.fetch`"}
    end
  end

  test "a command that changed the tree is recorded; one that changed nothing is not",
       ctx do
    dir = tree()
    on_exit(fn -> File.rm_rf!(dir) end)

    # Prepare the tree the supported way. `jj git init` alone is not enough:
    # the mirror lives INSIDE the tree it watches, so a tree that does not
    # ignore `.autovcs/` makes every command look dirty — jj would try to
    # snapshot a 32 MiB fjall journal, refuse it, and record a change anyway.
    # That is the difference between a history and a receipt printer.
    {_init, 0} = request(ctx, ["vcs", "init"], dir)
    assert File.read!(Path.join(dir, ".gitignore")) =~ ".autovcs/"

    File.write!(Path.join(dir, "prog.bl"), prog(dir))

    {out, code} = request(ctx, ["run", "prog.bl"], dir)
    assert code == 0, "the run must succeed; it said:\n#{out}"

    # The file is there because the program wrote it…
    assert File.read!(Path.join(dir, "made.txt")) == "1\n"

    # …and the fact layer knows, in the tree the CLIENT named.
    assert File.exists?(Path.join([dir, ".autovcs", "mirror.fjall"])),
           "the mirror must live in the client's tree"

    # Recorded, once, and the question history has to answer is *why*: the
    # command line is the reason. Nothing describes this tree yet — the file the
    # test just wrote is not a fact until a command has run over it.
    assert described(ctx.jj, dir) == ["bl: run prog.bl"],
           "the run must be one recorded change; it says: #{inspect(described(ctx.jj, dir))}"

    # Running it again writes the same bytes: nothing changed, so nothing is
    # recorded. A history that grows on every keystroke is not a history, so
    # this is asserted on what the changes SAY, not on how many there are — jj
    # abandons and recreates empty working-copy commits of its own accord.
    {out2, code2} = request(ctx, ["run", "prog.bl"], dir)
    assert code2 == 0, "the second run must succeed; it said:\n#{out2}"
    assert described(ctx.jj, dir) == ["bl: run prog.bl"], "an unchanged run must not be recorded"

    # Which jj runs is decided in one place, and it is not the PATH: the daemon
    # resolves the same vendored pin a CLI user gets.
    {bin, 0} = request(ctx, ["eval", "(vcs.jj/bin)"], dir)
    assert bin =~ "jj/bin/jj", "the daemon must resolve the pinned jj, not PATH; it said: #{bin}"
  end

  # The program writes by ABSOLUTE path on purpose: a relative path inside a
  # daemon-served request resolves against the daemon VM's own working
  # directory, not the client's `cwd` — the runtime binds `BeamLisp/cwd` for
  # what it resolves itself, and this is not that. The mutation is what this
  # test is about, so it names the file outright.
  defp prog(dir) do
    "(ns prog)\n(File/write! \"#{Path.join(dir, "made.txt")}\" \"1\\n\")\n(println \"wrote\")\n"
  end

  # ── the tree under test ──

  # A throwaway workspace. `bl vcs init` (driven over the daemon, above) is what
  # makes it a jj repo; this is only the empty directory, so the test never
  # reimplements what the feature does.
  defp tree do
    dir = Path.join(System.tmp_dir!(), "bl-vcs-#{:erlang.unique_integer([:positive])}")
    File.mkdir_p!(dir)
    dir
  end

  # What the changes SAY. The count of changes is not a fact a caller can rely
  # on — jj abandons and recreates its own empty working-copy commits — but a
  # description is: it is the reason the change exists.
  defp described(jj, dir) do
    jj
    |> log(dir, ["log", "-r", "all()", "--no-graph", "-T", "description.first_line() ++ \"\\n\""])
    |> String.split("\n", trim: true)
    # jj renders an empty description as "(empty)"; that is jj talking, not a reason.
    |> Enum.reject(&(&1 in ["", "(empty)"]))
  end

  defp log(jj, dir, args) do
    {out, 0} = System.cmd(jj, args, cd: dir, stderr_to_stdout: true)
    out
  end

  defp jj_bin, do: Path.join([to_string(:code.priv_dir(:beam_lisp)), "jj", "bin", "jj"])

  # ── the socket ──
  # The request/collect/connect trio is the daemon suite's own; a request is a
  # hello, a token, an argv and a cwd — the same frames `bl` sends.

  defp request(ctx, argv, cwd) do
    {:ok, sock} = connect(ctx.ep.sock)
    send_frame(sock, Protocol.encode({:bl, 1, :hello, %{tree: ctx.tree, token: ctx.token}}))
    {:ok, {:bl, 1, :ready, _}} = recv_frame(sock)

    id = :crypto.strong_rand_bytes(16)
    send_frame(sock, Protocol.encode({:bl, 1, :request, id, %{argv: argv, cwd: cwd, env_paths: []}}))

    result = collect(sock, id, "")
    :gen_tcp.close(sock)
    result
  end

  defp collect(sock, id, acc) do
    case recv_frame(sock) do
      {:ok, {:bl, 1, :stdout, ^id, _seq, bytes}} -> collect(sock, id, acc <> bytes)
      {:ok, {:bl, 1, :stderr, ^id, _seq, bytes}} -> collect(sock, id, acc <> bytes)
      {:ok, {:bl, 1, :exit, ^id, code}} -> {acc, code}
      {:ok, {:bl, 1, :failed, ^id, code, _}} -> {acc, code}
      {:ok, _other} -> collect(sock, id, acc)
      {:error, _} -> {acc, :closed}
    end
  end

  defp connect(sock_path) do
    :gen_tcp.connect({:local, String.to_charlist(sock_path)}, 0, [
      {:inet_backend, :inet},
      :local,
      :binary,
      {:packet, 4},
      {:active, false}
    ])
  end

  defp send_frame(sock, bin), do: :ok = :gen_tcp.send(sock, bin)

  defp recv_frame(sock) do
    case :gen_tcp.recv(sock, 0, 30_000) do
      {:ok, bin} -> {:ok, :erlang.binary_to_term(bin)}
      other -> other
    end
  end

  defp wait_for(fun, tries \\ 100)
  defp wait_for(_fun, 0), do: :timeout

  defp wait_for(fun, tries) do
    if fun.() do
      :ok
    else
      Process.sleep(20)
      wait_for(fun, tries - 1)
    end
  end
end
