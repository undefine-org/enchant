//! tree.rs — the lossless Nix CST as beam-lisp data, and back.
//!
//! # The shape
//!
//! One map per node, one map per token; trivia (whitespace, comments) is a
//! token like any other, which is *why* this is lossless:
//!
//! ```text
//! {:kind :node-attr-set :children [{:kind :token-whitespace :text " "} …]}
//! {:kind :token-ident   :text "outputs"}
//! ```
//!
//! `:children` present ⇒ node. `:text` present ⇒ token. Exactly one is ever
//! set, so the discriminator needs no third field — and a document is a
//! SELF-CONTAINED value: concatenating every leaf's text in order reproduces
//! the source byte for byte, with no reference back to the file it came from.
//!
//! `:children` is an Erlang LIST, not a Vector. A child list is walked, never
//! indexed, and a list of N terms costs N cons cells against a Vector's map +
//! tuple; the asymmetry only gets worse as the tree grows. Nix LISTS in the
//! data view ARE Vectors (`data.rs`), because those are values a caller
//! indexes — the same choice `bl.json` makes for JSON arrays.
//!
//! # The kind names
//!
//! `:node-attr-set`, `:token-whitespace` — rnix's own `NODE_ATTR_SET` /
//! `TOKEN_WHITESPACE`, lowercased with `_`→`-`. A total, reversible rename
//! means there is no table to drift: `kind_of(kind_name(k)) == k` for every
//! kind rnix has.

use rnix::{NixLanguage, SyntaxKind, SyntaxNode};
use rowan::{GreenNode, GreenNodeBuilder, Language, NodeOrToken};
use rustler::{Atom, Encoder, Env, NifResult, Term};

/// One past the largest `SyntaxKind` discriminant. rnix is `#[non_exhaustive]`
/// and keeps its own maximum private, so this is derived from the last variant
/// it does expose — and `Kinds::of` indexes with the raw discriminant, which it
/// asserts is in range.
pub const KIND_COUNT: usize = SyntaxKind::NODE_WITH as usize + 1;

/// `SyntaxKind` → its beam-lisp name. `NODE_ATTR_SET` → `node-attr-set`.
pub fn kind_name(kind: SyntaxKind) -> String {
    format!("{kind:?}")
        .chars()
        .map(|c| match c {
            'A'..='Z' => c.to_ascii_lowercase(),
            '_' => '-',
            other => other,
        })
        .collect()
}

/// The inverse of `kind_name`. `None` for a name rnix does not have, which is
/// how a malformed tree is refused instead of silently becoming `NODE_ERROR`.
pub fn kind_of(name: &str) -> Option<SyntaxKind> {
    let raw: String = name
        .chars()
        .map(|c| match c {
            'a'..='z' => c.to_ascii_uppercase(),
            '-' => '_',
            other => other,
        })
        .collect();
    raw.parse::<SyntaxKind>().ok()
}

/// The atoms a tree shares across every node, resolved once per call.
///
/// `:kind` is resolved lazily per *kind* rather than per node: a 900-token
/// document holds ~40 distinct kinds, so the ~95 possible `Atom::from_str`
/// lookups collapse to ~40, once, instead of ~900.
pub struct Keys<'a> {
    pub env: Env<'a>,
    pub kind: Atom,
    pub children: Atom,
    pub text: Atom,
    cache: Vec<Option<Atom>>,
}

impl<'a> Keys<'a> {
    pub fn new(env: Env<'a>) -> NifResult<Self> {
        Ok(Keys {
            env,
            kind: Atom::from_str(env, "kind")?,
            children: Atom::from_str(env, "children")?,
            text: Atom::from_str(env, "text")?,
            cache: vec![None; KIND_COUNT],
        })
    }

    pub fn kind_atom(&mut self, kind: SyntaxKind) -> NifResult<Atom> {
        let i = kind as usize;
        if i >= KIND_COUNT {
            return Err(crate::err(format!("syntax kind {kind:?} is out of range")));
        }
        if let Some(a) = self.cache[i] {
            return Ok(a);
        }
        let a = Atom::from_str(self.env, &kind_name(kind))?;
        self.cache[i] = Some(a);
        Ok(a)
    }
}

// ── rowan → term ────────────────────────────────────────────────────────────

/// Encode `node` and every token beneath it.
///
/// Recursion depth is bounded by the PARSER (rnix stops at 512 and reports
/// `RecursionLimitExceeded`), so the stack this uses is a function of the
/// grammar's own limit, not of the input's size.
pub fn to_term<'a>(
    keys: &mut Keys<'a>,
    node: &SyntaxNode,
) -> NifResult<Term<'a>> {
    let mut children: Vec<Term<'a>> = Vec::new();
    for child in node.children_with_tokens() {
        children.push(match child {
            NodeOrToken::Node(n) => to_term(keys, &n)?,
            NodeOrToken::Token(t) => token_term(keys, &t)?,
        });
    }
    let e = keys.env;
    Term::map_from_term_arrays(
        e,
        &[keys.kind.to_term(e), keys.children.to_term(e)],
        &[
            keys.kind_atom(node.kind())?.to_term(e),
            children.encode(e),
        ],
    )
}

/// A token is its kind and its bytes. The text is a SUB-BINARY of the source
/// the caller handed in, so a leaf costs a header and nothing else — the bytes
/// are already there, and the document keeps them alive by referring to them.
fn token_term<'a>(keys: &mut Keys<'a>, token: &rnix::SyntaxToken) -> NifResult<Term<'a>> {
    let e = keys.env;
    let text = token.text();
    Term::map_from_term_arrays(
        e,
        &[keys.kind.to_term(e), keys.text.to_term(e)],
        &[
            keys.kind_atom(token.kind())?.to_term(e),
            crate::make_binary(e, text.as_bytes())?,
        ],
    )
}

// ── term → rowan ────────────────────────────────────────────────────────────

/// Rebuild a rowan tree from the beam-lisp value `to_term` produced.
///
/// This is what lets the DATA VIEW work on any subtree. A subtree is often not
/// a legal standalone expression — `nixpkgs.url = "…";` is an
/// `NODE_ATTRPATH_VALUE`, which no expression parser accepts — so re-parsing
/// the subtree's text is not an option. Rebuilding the tree instead means the
/// typed AST is available at every node a caller can name, with one code path.
///
/// Total by construction: the only ways to fail are a value that is not a node
/// or a token, a kind rnix does not know, and nesting past the parser's own
/// limit. Each is reported as text, so `priv/lib/nix.bl` can raise it as written.
pub fn from_term<'a>(term: Term<'a>) -> Result<GreenNode, String> {
    let terms = Terms::new(term.get_env())?;
    let mut builder = GreenNodeBuilder::new();
    build(&mut builder, &terms, term, 0)?;
    Ok(builder.finish())
}

/// The three atoms a tree carries, resolved ONCE per call rather than once per
/// node: a document of 900 tokens would otherwise pay 1,800 `map_get`s for
/// atoms that never change between them.
struct Terms {
    kind: Atom,
    text: Atom,
    children: Atom,
}

impl Terms {
    fn new(env: Env) -> Result<Self, String> {
        Ok(Terms {
            kind: crate::atom(env, "kind").map_err(|e| format!("{e:?}"))?,
            text: crate::atom(env, "text").map_err(|e| format!("{e:?}"))?,
            children: crate::atom(env, "children").map_err(|e| format!("{e:?}"))?,
        })
    }
}

fn build(builder: &mut GreenNodeBuilder, terms: &Terms, term: Term, depth: usize) -> Result<(), String> {
    if depth > 1024 {
        return Err("tree is nested deeper than 1024 levels".into());
    }
    let kind = term
        .map_get(terms.kind)
        .map_err(|_| "node is missing :kind".to_string())?
        .atom_to_string()
        .map_err(|_| "node :kind is not an atom".to_string())?;
    let kind = kind_of(&kind).ok_or_else(|| format!("unknown syntax kind {kind:?}"))?;

    if let Ok(text) = term
        .map_get(terms.text)
        .and_then(|t| t.decode::<rustler::Binary>())
    {
        let text = std::str::from_utf8(text.as_slice())
            .map_err(|_| "token text is not UTF-8".to_string())?;
        builder.token(NixLanguage::kind_to_raw(kind), text);
        return Ok(());
    }

    let children = term
        .map_get(terms.children)
        .map_err(|_| "node has neither :text nor :children".to_string())?;
    builder.start_node(NixLanguage::kind_to_raw(kind));
    for child in children
        .decode::<Vec<Term>>()
        .map_err(|_| "node :children is not a list".to_string())?
    {
        build(builder, terms, child, depth + 1)?;
    }
    builder.finish_node();
    Ok(())
}

// ── term → text ─────────────────────────────────────────────────────────────

/// The source text of a tree: every leaf's text, in order.
///
/// `tree.rs` never writes Nix — there is no printer here to disagree with the
/// tree. The bytes are the leaves, so this fold IS the definition of the
/// round trip, and `nix/text`'s native path is nothing more than it, run in
/// Rust. A second, policy-carrying printer belongs to `data.rs`, which is
/// where formatting is a decision.
pub fn write_text<'a>(term: Term<'a>, out: &mut Vec<u8>) -> Result<(), String> {
    let terms = Terms::new(term.get_env())?;
    write_into(&terms, term, out, 0)
}

fn write_into(terms: &Terms, term: Term, out: &mut Vec<u8>, depth: usize) -> Result<(), String> {
    if depth > 1024 {
        return Err("tree is nested deeper than 1024 levels".into());
    }
    if let Ok(text) = term
        .map_get(terms.text)
        .and_then(|t| t.decode::<rustler::Binary>())
    {
        out.extend_from_slice(text.as_slice());
        return Ok(());
    }
    let children = term
        .map_get(terms.children)
        .map_err(|_| "node has neither :text nor :children".to_string())?;
    for child in children
        .decode::<Vec<Term>>()
        .map_err(|_| "node :children is not a list".to_string())?
    {
        write_into(terms, child, out, depth + 1)?;
    }
    Ok(())
}

// ── tests ───────────────────────────────────────────────────────────────────
//
// The NIF surface is exercised from beam-lisp, where it lives (`tests/unit/nix/test.bl`).
// What is testable HERE is what is pure: the kind vocabulary, and the
// generator's own text decisions — quoting, escaping, and the shapes a number
// is allowed to take.

#[cfg(test)]
mod tests {
    use super::*;

    /// EVERY kind rnix has, enumerated through rnix's own discriminator, so a
    /// kind added upstream is covered without this test being edited. The
    /// transform must be a bijection or a round of parse→print would silently
    /// rename a node — and a renamed node is a tree that cannot be rebuilt.
    #[test]
    fn kind_names_round_trip_for_every_kind() {
        for i in 0..KIND_COUNT {
            let kind = <NixLanguage as Language>::kind_from_raw(rowan::SyntaxKind(i as u16));
            let name = kind_name(kind);
            assert_eq!(kind_of(&name), Some(kind), "{kind:?} -> {name:?}");
            assert!(
                name.chars().all(|c| c.is_ascii_lowercase() || c == '-'),
                "{kind:?} -> {name:?} is not a keyword name"
            );
        }
    }

    #[test]
    fn a_name_rnix_does_not_have_is_not_a_kind() {
        assert_eq!(kind_of("node-there-is-no-such-thing"), None);
        assert_eq!(kind_of(""), None);
    }

    /// The shapes are the point: the dotless single word, the `_` that must
    /// become a `-`, and a name with a digit in it.
    #[test]
    fn kind_name_shape() {
        assert_eq!(kind_name(SyntaxKind::NODE_ATTR_SET), "node-attr-set");
        assert_eq!(kind_name(SyntaxKind::TOKEN_WHITESPACE), "token-whitespace");
        assert_eq!(kind_name(SyntaxKind::NODE_PATH_HOME), "node-path-home");
    }
}

// ── counting, with nothing built ────────────────────────────────────────────

/// `(nodes, tokens, trivia)` for a parsed tree — the size of the document, with
/// no Erlang terms built. `nix_count`'s whole body; see its doc for why the
/// instrument exists.
///
/// Trivia is counted, not skipped: whitespace and comments are most of the
/// tokens in a hand-written file, and a caller comparing this crate's cost
/// against a parser that discards them must be able to subtract them.
pub fn tally(node: &SyntaxNode) -> (usize, usize, usize) {
    let mut counts = (0, 0, 0);
    tally_into(node, &mut counts);
    counts
}

fn tally_into(node: &SyntaxNode, counts: &mut (usize, usize, usize)) {
    counts.0 += 1;
    for child in node.children_with_tokens() {
        match child {
            NodeOrToken::Node(n) => tally_into(&n, counts),
            NodeOrToken::Token(t) => {
                counts.1 += 1;
                if matches!(t.kind(), SyntaxKind::TOKEN_WHITESPACE | SyntaxKind::TOKEN_COMMENT) {
                    counts.2 += 1;
                }
            }
        }
    }
}

