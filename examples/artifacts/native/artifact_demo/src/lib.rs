#[rustler::nif]
fn answer() -> u32 { 42 }

rustler::init!("Elixir.BeamLisp.Native.Artifact.Showcase");
