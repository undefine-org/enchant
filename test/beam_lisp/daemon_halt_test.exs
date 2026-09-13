defmodule BeamLisp.DaemonHaltTest do
  @moduledoc """
  A request may not end the VM it shares: `(System/halt n)`, and the silent
  failure the daemon used to relay as a bare exit with no explanation.

  `System.halt` is `:erlang.halt/1` — a BIF, uncatchable, invisible to the
  executor's `rescue`. Before this, one served program could end a session's
  warmth for every request after it, and the client only learned that the
  connection went away. The fix is a DENY in the request env (`Env.restricted`),
  which beats `:all` because a grant of "everything" cannot say "not this one".

  Three facts, and why each is the one asserted:

    * the request fails NON-ZERO — a refusal is a failure, not a silent success;
    * the client reads the REFUSAL itself, from the daemon — the message names
      the refused fn, so the fix is visible where the program was written;
    * the daemon still answers the NEXT request — the property the whole thing
      exists for, and the only one that distinguishes this from a lucky crash.

  The fourth case is the other half of the same bug: a failure's REASON must
  reach the client at all. `io-err` wrote to the `:standard_error` device, which
  belongs to the whole VM, so every served diagnostic landed on the daemon's
  console and the client saw a bare non-zero exit. It writes to the group leader
  now, and the daemon keeps a last-resort line for a command that truly said
  nothing — asserted to stay OUT of the way when the command spoke.
  """

  use ExUnit.Case, async: false

  # The wire (a request, and collecting what it said) is shared with the other
  # daemon tests: BeamLisp.Test.DaemonSocket.
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

    {:ok, root: root, ep: ep, token: File.read!(ep.token), tree: Paths.tree_fingerprint(root)}
  end

  test "a served program that halts the VM is refused, and the daemon survives", ctx do
    dir = tree()
    on_exit(fn -> File.rm_rf!(dir) end)

    # The refusal reaches the client as a compile error NAMING the fn. Through
    # `eval` the compile happens on the request's own worker, so the message is
    # framed to the client like any other output.
    {out, code} = request(ctx, ["eval", "(System/halt 3)"], dir)

    # A refusal is a failure: the exit code must not be the 3 the program asked
    # for, because the program did not get its way.
    assert is_integer(code) and code != 0,
           "a refused halt must fail; it exited #{inspect(code)} saying:\n#{out}"

    assert out =~ "System.halt" and out =~ "denied",
           "the client must read the refusal; it said:\n#{out}"

    # The point of the whole exercise: the VM is still there, and still serves.
    assert Process.whereis(Server) != nil, "the daemon must survive a refused halt"

    {out2, code2} = request(ctx, ["eval", "(+ 1 2)"], dir)
    assert code2 == 0, "the next request must still succeed; it said:\n#{out2}"
    assert out2 =~ "3", "the next request must return its value; it said:\n#{out2}"

    # Through a FILE: the same call is refused (the tree was never touched) and
    # the daemon survives it. The wording is not asserted here — a diagnostic
    # raised while the LOADER compiles the file is printed by that process, so
    # it lands on the daemon's console rather than in the client's frames. That
    # gap is filed; this test asserts what the client can rely on today.
    File.write!(Path.join(dir, "halt.bl"), "(ns prog)\n(println \"before\")\n(System/halt 3)\n")
    {outf, codef} = request(ctx, ["run", "halt.bl"], dir)

    assert is_integer(codef) and codef != 0,
           "a file that halts must fail too; it exited #{inspect(codef)} saying:\n#{outf}"

    assert outf =~ "before", "output before the refusal must still arrive; it said:\n#{outf}"
    assert Process.whereis(Server) != nil, "the daemon must survive a refused halt in a file"

    # …and the OTHER VM-enders are refused by the same policy, so the family is
    # closed rather than the one call nobody thought of.
    for expr <- ["(System/stop 3)", "(erlang/halt 3)", "(init/stop)"] do
      {o, c} = request(ctx, ["eval", expr], dir)
      assert c != 0, "#{expr} must be refused; it exited #{inspect(c)} saying:\n#{o}"
      assert Process.whereis(Server) != nil, "#{expr} must not end the daemon"
    end
  end

  test "a failing command explains itself to the CLIENT, not to the daemon's console", ctx do
    dir = tree()
    on_exit(fn -> File.rm_rf!(dir) end)

    # A file that is not there: the failure has no output of its own from the
    # program, and the diagnostic is the CLI's. It must arrive in the client's
    # frames — `io-err` writes to the group leader, which for a request is the
    # io proxy — or the client sees a bare non-zero exit and the reason stays on
    # the daemon's console, where the user will never look.
    {out, code} = request(ctx, ["run", Path.join(dir, "missing.bl")], dir)

    assert is_integer(code) and code != 0, "a missing file must fail; it exited #{inspect(code)}"

    assert out =~ "could not read file",
           "the client must read the reason; it said:\n#{out}"

    # …and the daemon's last-resort diagnostic stays out of the way when the
    # command explained itself. Two messages for one failure is one too many.
    refute out =~ "without writing anything",
           "a command that spoke must not also get the silent-failure line; it said:\n#{out}"
  end

  # The wire this file used to carry — request/collect/connect/tree/wait_for —
  # is shared now: BeamLisp.Test.DaemonSocket.
end
