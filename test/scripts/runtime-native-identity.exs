# The identity is reported by executing the actually loaded NIF. Atomically
# changing its disk pathname must not rewrite the running native implementation.
Application.ensure_all_started(:crypto)
loaded = BeamLisp.LazyMemo.runtime_identity!()
unless is_binary(loaded) and byte_size(loaded) == 64, do: raise("invalid native build identity")
target = BeamLisp.AOT.runtime_image_key()
library = "lib/beam_lisp-0.1.0/priv/native/lazy_memo.so"
saved = library <> ".loaded-original"
File.rename!(library, saved)
try do
  File.cp!(library <> ".variant", library)
  ^loaded = BeamLisp.LazyMemo.runtime_identity!()
  ^target = BeamLisp.AOT.runtime_image_key()
  # It remains a real functioning native runtime, rather than a fake probe.
  resource = BeamLisp.LazyMemo.create(42)
  42 = BeamLisp.LazyMemo.read(resource)
after
  File.rm!(library)
  File.rename!(saved, library)
end
IO.puts("NATIVE-RUNTIME loaded-owner=true path-replacement-does-not-rebind=true identity=#{loaded}")
