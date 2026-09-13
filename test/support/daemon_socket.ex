defmodule BeamLisp.Test.DaemonSocket do
  @moduledoc """
  The wire, in one place: a test that drives the daemon the way a client does.

  A request is a hello carrying the tree fingerprint and the token, then an
  argv and a cwd — the same frames `bl` sends. Three daemon tests need exactly
  these functions, and a private copy of the protocol in each would be three
  copies that drift; the reason each test file exists is the BEHAVIOUR, not the
  framing.

  Import it (`import BeamLisp.Test.DaemonSocket`) and call `request/3`,
  `tree/0`, `wait_for/2` as if they were local.

  `collect/3` folds stdout and stderr into one accumulator: what a test asserts
  is what the client READ, not which stream won a race. A test that cares about
  the distinction would need the frames separately — see BUG-039, where the
  request path currently has no stderr frame of its own.
  """

  alias BeamLisp.Daemon.Protocol

  @doc """
  A directory of its own for the tree under test — daemon tests assert on what
  a command DID to a tree, so sharing one would make them order-dependent.
  """
  def tree do
    dir = Path.join(System.tmp_dir!(), "bl-daemon-#{:erlang.unique_integer([:positive])}")
    File.mkdir_p!(dir)
    dir
  end

  @doc """
  Send one request and return `{output, exit_code}`.

  `:closed` as the code means the daemon dropped the connection — the shape a
  dead VM produces, which is why the halt test can tell a refusal from a crash.
  """
  def request(ctx, argv, cwd) do
    {:ok, sock} = connect(ctx.ep.sock)
    send_frame(sock, Protocol.encode({:bl, 1, :hello, %{tree: ctx.tree, token: ctx.token}}))
    {:ok, {:bl, 1, :ready, _}} = recv_frame(sock)

    id = :crypto.strong_rand_bytes(16)

    send_frame(
      sock,
      Protocol.encode({:bl, 1, :request, id, %{argv: argv, cwd: cwd, env_paths: []}})
    )

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

  def wait_for(fun, tries \\ 100)
  def wait_for(_fun, 0), do: :timeout

  def wait_for(fun, tries) do
    if fun.() do
      true
    else
      Process.sleep(20)
      wait_for(fun, tries - 1)
    end
  end
end
