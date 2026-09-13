defmodule BeamLisp.DaemonCwdTest do
  @moduledoc """
  Where a served program's relative path lands.

  A relative path means what it means in a shell: relative to where the COMMAND
  was run. The daemon runs in the tree it serves, and a BEAM VM's working
  directory is global — one value for the whole VM, shared with the watcher,
  the gateway and every other request — so before this a served
  `(File/write! "made.txt" …)` wrote into the daemon's own checkout. The
  program said one thing and the filesystem did another, and which tree a
  program touched depended on which process happened to run it.

  The fix is not a `chdir` (that would move the ground under every concurrent
  component): `RT.host_call/3` resolves the arguments that NAME A PATH against
  the command's cwd, per the same table the capability gate audits.

  The acceptance cannot pass by accident: the request's cwd is a directory
  OUTSIDE the daemon's tree, so a resolution that falls back to the tree root —
  or to nothing at all — fails the assertions below.
  """

  use ExUnit.Case, async: false

  # The wire (a request, and collecting what it said) is shared with the other
  # daemon tests.
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

  test "a served program's relative paths resolve where the COMMAND was run", ctx do
    dir = tree()

    # A failing run must not leave the wrong tree dirty, so the two paths the
    # assertions check for absence are cleaned up either way.
    on_exit(fn ->
      File.rm_rf!(Path.join([ctx.root, "nested"]))
      File.rm_rf!(Path.join(ctx.root, "sibling.txt"))
      File.rm_rf!(dir)
    end)

    prog = Path.join(dir, "writes.bl")

    File.write!(prog, """
    (File/mkdir_p "nested")
    (File/write! "nested/made.txt" "one\\n")
    (File/write! "./sibling.txt" "two\\n")
    (println "done")
    """)

    {out, code} = request(ctx, ["run", prog], dir)
    assert code == 0, "expected a clean run, got #{inspect(code)}: #{out}"

    assert File.read!(Path.join([dir, "nested", "made.txt"])) == "one\n"
    assert File.read!(Path.join(dir, "sibling.txt")) == "two\n"

    # The other half of the claim: they are NOT in the tree the daemon serves,
    # which is where the VM's own cwd points — and where they landed before.
    refute File.exists?(Path.join([ctx.root, "nested", "made.txt"])),
           "a relative path wrote into the daemon's own checkout"

    refute File.exists?(Path.join(ctx.root, "sibling.txt")),
           "a relative path wrote into the daemon's own checkout"
  end

  test "an absolute path is left exactly as it was", ctx do
    dir = tree()
    on_exit(fn -> File.rm_rf!(dir) end)

    target = Path.join(dir, "absolute.txt")
    prog = Path.join(dir, "abs.bl")
    File.write!(prog, "(File/write! \"#{target}\" \"here\\n\")\n")

    {out, code} = request(ctx, ["run", prog], dir)
    assert code == 0, "expected a clean run, got #{inspect(code)}: #{out}"
    assert File.read!(target) == "here\n"
  end
end
