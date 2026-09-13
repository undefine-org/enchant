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

  # The wire (a request, and collecting what it said) is shared: the framing is
  # not what this file is about.
  import BeamLisp.Test.DaemonSocket

  alias BeamLisp.Daemon.{Paths, Server}


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

  # The program writes a RELATIVE path, and that is load-bearing: the request's
  # cwd is the tree under test, while the daemon's own cwd is this checkout — so
  # if a relative path resolved against the VM instead of against the command,
  # the change would land in the wrong tree and the log asserted below would be
  # empty (BUG-038, and the reason `RT.host_call` exists).
  defp prog(_dir) do
    "(ns prog)\n(File/write! \"made.txt\" \"1\\n\")\n(println \"wrote\")\n"
  end

  # ── the tree under test ──

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

  # The wire is shared: BeamLisp.Test.DaemonSocket (tree/request/collect/…).
end
