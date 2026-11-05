#!/usr/bin/env python3
"""Instrument launcher seams without changing an immutable coordinator image."""
import argparse
from pathlib import Path


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('coordinator', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
coordinator = args.coordinator.resolve(strict=True)
args.output.mkdir(parents=True, exist_ok=False)
output = args.output.resolve()
replacement = '''timed = fn label, action ->
  started = System.monotonic_time(:microsecond)
  try do action.() after
    IO.puts(:stderr, "STARTUP-PHASE " <> Jason.encode!(%{stage: label,
      elapsed_us: System.monotonic_time(:microsecond)-started}))
  end
end
fetch = fn ns, name ->
  value = BeamLisp.Env.fetch!(ns, name)
  Process.put({:profile_name, value}, ns <> "/" <> name)
  value
end
invoke = BeamLisp.Launcher.default_seam(:invoke)
seams = %{
  start_app: fn -> timed.("application", fn -> Application.ensure_all_started(:beam_lisp) end) end,
  ensure_loaded: fn ns -> timed.("load:" <> ns, fn -> BeamLisp.Loader.ensure_loaded(ns) end) end,
  fetch: fetch,
  invoke: fn value, argv -> timed.(Process.get({:profile_name, value}, "invoke"), fn -> invoke.(value, argv) end) end
}
BeamLisp.Launcher.start_app!(System.argv(), seams)'''
boot = (coordinator / 'boot.exs').read_text()
marker = 'BeamLisp.Launcher.start_app!(System.argv(), %{})'
assert boot.count(marker) == 1
(output / 'boot.exs').write_text(boot.replace(marker, replacement))
wrapper = (coordinator / 'bin/bl').read_text()
old = str(coordinator / 'boot.exs')
assert wrapper.count(old) == 1
(output / 'bl').write_text(wrapper.replace(old, str(output / 'boot.exs')))
(output / 'bl').chmod(0o755)
