//! `bl_nix` — Nix, as data, for beam-lisp.
//!
//! The native half of `priv/lib/nix/native.bl`: declared there, harnessed in
//! `priv/lib/nix.bl`, exercised by `test/bl/nix_test.bl`.
//!
//! # What this is for
//!
//! Build and deployment descriptions use `.nix` files: a flake, a lock, a systemd
//! unit. As text it can be copied and it can be shipped, and that is all. This
//! crate makes it a VALUE — parseable, addressable, editable and generatable
//! from beam-lisp — without giving up a single byte of what was written.
//!
//! # The split
//!
//! bl DECIDES; Rust WALKS. Every policy stays in `priv/lib/nix.bl`: which paths name
//! what, what an edit means, how a document is read from and written to disk,
//! what an error says. This crate owns two things and no others:
//!
//! - the GRAMMAR. Nix is parsed by `rnix`, a rowan-based CST parser with the
//!   whole language in it — indented strings, `''${…}''` escapes, path
//!   literals, `?` defaults, `@` binds, `let`/`with`/`rec`, operator
//!   precedence. A hand-written parser in bl would be a fifth of the size and
//!   wrong in the ways that matter, silently, on the files nobody tests.
//! - the BYTE LOOP. A tree walk written in beam-lisp costs a call per node,
//!   and a `.nix` document holds thousands of them. MEASURED (`scripts/nix-bench.bl`,
//!   medians of 51, six runs, some on a host another build was using): the
//!   beam-lisp fold runs 50–160x the native printer. The millisecond moves —
//!   print of an 873-byte flake measured 0.03 and 0.07 ms native, 2.4 and
//!   4.5 ms folded — the ORDER does not.
//!
//!   `nix/fold-text` is that same fold in beam-lisp, so the ratio is the
//!   Rust/BEAM boundary and nothing else: two implementations of one job,
//!   compared. Parsing has no beam-lisp rival to compare against, and that is
//!   the point — the GRAMMAR is why it is native, not the clock. Carrying the
//!   built tree across the boundary costs 1.4–2.0x the bare parse (`nix-count`
//!   parses and builds nothing).
//!
//! # Two laws, and nothing else is promised
//!
//! 1. **Lossless.** `(= src (nix/text (nix/read src)))` for EVERY input. The
//!    tree carries its trivia — whitespace and comments are tokens — so the
//!    source is recoverable from the value alone and needs no file beside it.
//! 2. **Data is a fixed point.** `(= (nix/data d) (nix/data (nix/read
//!    (nix/emit (nix/data d)))))`. `nix/data` refuses what it cannot represent
//!    (a lambda, a `let`), or, asked to, keeps it verbatim as `{:nix/expr …}`
//!    — so the value that comes back out is the value that went in.
//!
//! # What is deliberately NOT here
//!
//! An evaluator. Nix is lazy and Turing-complete; this crate never runs a Nix
//! expression and never guesses what one would produce. `nix/data` is a
//! projection of the parts that ARE data, and it stops at the first thing that
//! is not — naming the kind and the offset — because a projection that invents
//! a value for `pkgs.lib.optional` is how a wrong document gets written.
//! `:unsupported :tag` is the honest alternative: keep the source, claim
//! nothing about its meaning.
//!
//! Nor is there a printer for the syntax tree. `nix/text` concatenates the
//! leaves, which by construction is the input; a second printer for the same
//! job would be a second thing to disagree with. Where writing IS a decision —
//! generating a fresh document from beam-lisp values — that is `data.rs`, and
//! it is the inverse of the projection rather than a formatter for the parse.

mod data;
mod tree;

use rnix::Root;
use rustler::types::atom::Atom;
use rustler::types::tuple::make_tuple;
use rustler::{Binary, Encoder, Env, NifResult, Term};

pub fn err(msg: impl std::fmt::Display) -> rustler::Error {
    rustler::Error::Term(Box::new(format!("{}", msg)))
}

/// An atom by name. Every name this crate asks for is a constant it wrote
/// itself, so there is no untrusted-interning hazard on this path.
pub fn atom<'a>(env: Env<'a>, name: &str) -> NifResult<Atom> {
    Atom::from_str(env, name)
}

/// A BEAM binary in ONE call: `enif_make_new_binary` returns the term and a
/// pointer to its payload, so the bytes are written straight in. The safe path
/// (`Encoder for str`) allocates, copies, releases and wraps — three crossings
/// of the same boundary for one string.
///
/// Unsafe by necessity, and bounded by one rule: the pointer is valid only
/// until the next allocation, so it is filled immediately and nothing else.
pub fn make_binary<'a>(env: Env<'a>, bytes: &[u8]) -> NifResult<Term<'a>> {
    let mut term = std::mem::MaybeUninit::uninit();
    let buf =
        unsafe { rustler::sys::enif_make_new_binary(env.as_c_arg(), bytes.len(), term.as_mut_ptr()) };
    if buf.is_null() {
        return Err(err("binary allocation failed"));
    }
    unsafe { std::ptr::copy_nonoverlapping(bytes.as_ptr(), buf, bytes.len()) };
    Ok(unsafe { Term::new(env, term.assume_init()) })
}

/// A bl Vector: an Erlang map with a `__struct__` key whose `items` is a TUPLE.
///
/// Duplicated from `lib/beam_lisp/vector.ex` a second time (`bl_json` carries
/// the first). It is a cross-language contract, so it is written once here and
/// named in both places — the alternative, a crate-to-crate dependency to share
/// four lines, would be worse.
pub fn make_vector<'a>(
    env: Env<'a>,
    items: Vec<Term<'a>>,
    struct_k: Atom,
    items_k: Atom,
    vec_mod: Atom,
) -> NifResult<Term<'a>> {
    let tuple = make_tuple(env, &items);
    Term::map_from_term_arrays(
        env,
        &[struct_k.to_term(env), items_k.to_term(env), atom(env, "meta")?.to_term(env)],
        &[vec_mod.to_term(env), tuple, rustler::types::atom::nil().to_term(env)],
    )
}

/// The marker `vm.native/available?` calls to tell a loaded NIF from the
/// unloaded stub. A stub that answered true would make an absent crate
/// indistinguishable from a present one.
#[rustler::nif]
fn __nif_loaded__() -> bool {
    true
}

// ── positions and refusals ──────────────────────────────────────────────────

/// A byte offset reported three ways, because the three answer different
/// questions: `offset` indexes the source, `line`/`column` are what an editor
/// and a human want. The column counts CHARACTERS, not bytes — a file whose
/// comment holds an em dash must not report a column that points at the wrong
/// place.
fn position(src: &str, offset: usize) -> (usize, usize, usize) {
    let offset = offset.min(src.len());
    let head = &src[..offset];
    let line = head.matches('\n').count() + 1;
    let column = head.rsplit('\n').next().unwrap_or("").chars().count() + 1;
    (offset, line, column)
}

/// `%{offset: n, line: n, column: n}` — where the refusal happened.
fn pos_map<'a>(env: Env<'a>, src: &str, offset: usize) -> NifResult<Term<'a>> {
    let (offset, line, column) = position(src, offset);
    Term::map_from_term_arrays(
        env,
        &[
            atom(env, "offset")?.to_term(env),
            atom(env, "line")?.to_term(env),
            atom(env, "column")?.to_term(env),
        ],
        &[offset.encode(env), line.encode(env), column.encode(env)],
    )
}

/// `%{message: …, where: %{offset: …, line: …, column: …}, …extra}`.
///
/// ONE shape for every refusal this crate makes — a parse error, a value the
/// projection cannot represent, a value the generator has no Nix spelling for.
/// A caller renders a refusal once, and the fields a caller can branch on
/// (`:reason`, `:kind`, `:path`) are the ones that name WHAT was refused rather
/// than paraphrasing it.
///
/// `where` is present only when `at` is: a position is meaningful against the
/// text it indexes, and a subtree indexes only itself. A whole document's
/// refusal points into the file; a fragment's points at nothing a caller can
/// use, and a plausible-looking wrong line is worse than no line.
fn refusal<'a>(
    env: Env<'a>,
    message: &str,
    src: &str,
    at: Option<usize>,
    extra: Vec<(&str, Term<'a>)>,
) -> NifResult<Term<'a>> {
    let mut keys = vec![atom(env, "message")?.to_term(env)];
    let mut vals = vec![make_binary(env, message.as_bytes())?];
    if let Some(at) = at {
        keys.push(atom(env, "where")?.to_term(env));
        vals.push(pos_map(env, src, at)?);
    }
    for (k, v) in extra {
        keys.push(atom(env, k)?.to_term(env));
        vals.push(v);
    }
    Term::map_from_term_arrays(env, &keys, &vals)
}

/// `{:ok value}` / `{:error refusal}`.
fn ok_reply<'a>(env: Env<'a>, value: Term<'a>) -> NifResult<Term<'a>> {
    Term::map_from_term_arrays(env, &[atom(env, "ok")?.to_term(env)], &[value])
}

fn error_reply<'a>(env: Env<'a>, detail: Term<'a>) -> NifResult<Term<'a>> {
    Term::map_from_term_arrays(env, &[atom(env, "error")?.to_term(env)], &[detail])
}

/// Read a boolean option, defaulting when the option is absent — the map is the
/// only place a default can live, since a NIF has no optional arity.
fn opt_bool<'a>(env: Env<'a>, opts: Term<'a>, name: &str, default: bool) -> bool {
    atom(env, name)
        .and_then(|a| opts.map_get(a))
        .and_then(|t| t.decode::<bool>())
        .unwrap_or(default)
}

/// Read an atom-valued option. A missing option and an unreadable one are the
/// same answer: the default. Validating what the caller MEANT is bl's job, and
/// bl passes a value it built itself.
fn opt_atom<'a>(env: Env<'a>, opts: Term<'a>, name: &str, default: &str) -> String {
    atom(env, name)
        .and_then(|a| opts.map_get(a))
        .and_then(|t| t.atom_to_string())
        .unwrap_or_else(|_| default.to_string())
}

// ── rnix parse errors, as one shape ─────────────────────────────────────────

/// Every `ParseError` variant carries a range EXCEPT the two end-of-file ones,
/// which have none — and the enum is `#[non_exhaustive]`, so the wildcard arm
/// is required rather than defensive. `src.len()` is the right offset for EOF:
/// it is where the parser stopped.
fn parse_error_offset(e: &rnix::ParseError, src: &str) -> usize {
    use rnix::ParseError::*;
    match e {
        Unexpected(r) | UnexpectedExtra(r) | UnexpectedDoubleBind(r) => usize::from(r.start()),
        UnexpectedWanted(_, r, _) | DuplicatedArgs(r, _) => usize::from(r.start()),
        UnexpectedEOF | UnexpectedEOFWanted(_) | RecursionLimitExceeded => src.len(),
        _ => src.len(),
    }
}

/// Source bytes as UTF-8, or the refusal that says why not.
fn utf8<'a>(env: Env<'a>, source: &Binary<'a>) -> Result<String, Term<'a>> {
    match std::str::from_utf8(source.as_slice()) {
        Ok(s) => Ok(s.to_string()),
        Err(e) => {
            let detail = refusal(
                env,
                &format!("source is not valid UTF-8 ({e})"),
                "",
                Some(e.valid_up_to()),
                vec![],
            );
            Err(detail.unwrap_or_else(|_| atom(env, "error").unwrap().to_term(env)))
        }
    }
}

// ── the NIF surface ─────────────────────────────────────────────────────────
//
// Five, and each earns its place. `options` is a map in every case: `defnative`
// binds an exact arity, so an optional argument would be a second name and a
// second stub to keep in step — and the policy that reads an option belongs in
// `priv/lib/nix.bl` anyway.

/// Parse Nix source into the lossless tree.
///
/// STRICT by default, and that is the point: `rnix` always produces a tree, and
/// with an error in the input that tree is a guess about intent. A codec that
/// returns a guess for a document with a typo in it is how a wrong document
/// gets written. `{:strict false}` asks for the tree regardless — an editor
/// wants to show a file that is being typed — and `nix/read` is where that
/// choice is made visible to a caller.
#[rustler::nif(schedule = "DirtyCpu")]
fn nix_parse<'a>(env: Env<'a>, source: Binary<'a>, opts: Term<'a>) -> NifResult<Term<'a>> {
    let src = match utf8(env, &source) {
        Ok(s) => s,
        Err(detail) => return error_reply(env, detail),
    };
    let parse = Root::parse(&src);
    if opt_bool(env, opts, "strict", true) {
        if let Some(first) = parse.errors().first() {
            let offset = parse_error_offset(first, &src);
            let detail = refusal(env, &format!("{first}"), &src, Some(offset), vec![])?;
            return error_reply(env, detail);
        }
    }
    let mut keys = tree::Keys::new(env)?;
    let node = tree::to_term(&mut keys, &parse.syntax())?;
    ok_reply(env, node)
}

/// The tree's own source text: every leaf, in order.
///
/// Not a formatter — a fold. `(= src (nix_print (nix_parse src)))` is therefore
/// a property of the DATA STRUCTURE rather than of a printer that could drift
/// from it.
#[rustler::nif(schedule = "DirtyCpu")]
fn nix_print<'a>(env: Env<'a>, node: Term<'a>) -> NifResult<Term<'a>> {
    let mut out = Vec::new();
    match tree::write_text(node, &mut out) {
        Ok(()) => ok_reply(env, make_binary(env, &out)?),
        Err(reason) => error_reply(env, refusal(env, &reason, "", None, vec![])?),
    }
}

/// The data view: the parts of a document that ARE data, as beam-lisp values.
///
/// Works on ANY subtree, not just a whole file. A subtree is often not a legal
/// standalone expression — `nixpkgs.url = "…";` is not — so the tree is rebuilt
/// here and the typed AST is taken from that, which is the same code path for
/// every node a caller can name.
///
/// `opts`: `%{keys: :string | :keyword | :existing_atom, unsupported: :throw |
/// :tag}`.
#[rustler::nif(schedule = "DirtyCpu")]
fn nix_data<'a>(env: Env<'a>, node: Term<'a>, opts: Term<'a>) -> NifResult<Term<'a>> {
    data::project(env, node, opts)
}

/// Fresh Nix source from beam-lisp values — the inverse of `nix_data`.
///
/// `opts`: `%{indent: integer}` (default 2).
#[rustler::nif(schedule = "DirtyCpu")]
fn nix_emit<'a>(env: Env<'a>, value: Term<'a>, opts: Term<'a>) -> NifResult<Term<'a>> {
    data::generate(env, value, opts)
}

/// PARSE ONLY: how big the document is, building no Erlang terms at all.
///
/// It exists so the cost of this crate can be MEASURED rather than argued —
/// `nix_parse` minus `nix_count` on the same bytes brackets what the Rust/BEAM
/// boundary costs, with the grammar held constant. `bl.json` has the same
/// instrument for the same reason: three wrong explanations for its decode gap
/// survived as long as they did because every available comparison was against
/// a DIFFERENT implementation.
#[rustler::nif(schedule = "DirtyCpu")]
fn nix_count<'a>(env: Env<'a>, source: Binary<'a>) -> NifResult<Term<'a>> {
    let src = match utf8(env, &source) {
        Ok(s) => s,
        Err(detail) => return error_reply(env, detail),
    };
    let parse = Root::parse(&src);
    let (nodes, tokens, trivia) = tree::tally(&parse.syntax());
    Term::map_from_term_arrays(
        env,
        &[
            atom(env, "nodes")?.to_term(env),
            atom(env, "tokens")?.to_term(env),
            atom(env, "trivia")?.to_term(env),
            atom(env, "errors")?.to_term(env),
        ],
        &[
            nodes.encode(env),
            tokens.encode(env),
            trivia.encode(env),
            parse.errors().len().encode(env),
        ],
    )
}

// The rustler contract.
//
// This string must equal `vm.native/host-module` for the declaring ns: here
// `nix.native` → `Elixir.BeamLisp.Native.Nix.Native`. Get it wrong and
// `load_nif` binds NOTHING while every stub stays in place, so each call
// raises `:nif_not_loaded` and the `.so` looks absent while sitting right
// there — the failure that cost `bl.json` a silent 40x.
rustler::init!("Elixir.BeamLisp.Native.Nix.Native");
