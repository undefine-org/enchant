#[rustler::nif]
fn answer() -> u32 {
    workspace_support::answer()
}

#[rustler::nif]
fn support_message() -> String {
    workspace_support::message().to_owned()
}

// The host follows the BL namespace, independently of Cargo/package/lib aliases.
rustler::init!("Elixir.BeamLisp.Native.Artifact.Workspace");
