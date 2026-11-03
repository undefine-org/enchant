//! data.rs — Nix that IS data, as beam-lisp values, and back again.
//!
//! # The projection
//!
//! ```text
//! { a = 1; b.c = [ 1 "two" ]; }   →   {"a" 1, "b" {"c" [1 "two"]}}
//! "text"                          →   "text"      (escapes decoded)
//! ''\n  text''                    →   "text"      (indentation stripped)
//! 1 / 1.5 / true / null           →   1 / 1.5 / true / nil
//! https://example.com             →   "https://example.com"   (Nix agrees: a URI IS a string)
//! ./relative  /abs  ~/home        →   {:nix/path "./relative"}
//! ( x )                           →   the projection of x     (parentheses are punctuation)
//! ```
//!
//! Everything else is REFUSED rather than approximated: `{ self, nixpkgs }: …`
//! has no value until it is APPLIED, `let x = 1; in x` has none until it is
//! EVALUATED, `"${v}"` has none until `v` is known. A projector that rendered
//! `pkgs.lib.optional` as a string would produce a document that reads
//! perfectly and means nothing.
//!
//! `rec` is refused with the rest, and it is the sharpest case for it. A `rec`
//! attrset LOOKS like data and projects to a plain map without complaint — but
//! the map has lost the recursion, and the data fixed point cannot notice,
//! because feeding that map back through `nix/emit` yields a non-`rec` attrset
//! that projects to the SAME map. Fidelity laws only catch what they can see;
//! this is a case they cannot, so it is refused on the way in.
//!
//! # `{:nix/expr …}` — the honest escape
//!
//! Under `{:unsupported :tag}`, a refused node is kept as
//! `{:nix/expr "<its source>"}`. That makes the projection TOTAL, and it makes
//! the escape SYMMETRIC: `nix_emit` splices that source back verbatim (in
//! parentheses, so it is legal wherever an expression is). Nothing is claimed
//! about what the text means — which is exactly the claim that is true.
//!
//! # The generation
//!
//! The inverse: maps become attrsets, vectors and lists become Nix lists,
//! strings are escaped, numbers are formatted exactly, `true`/`false`/`nil`
//! are the keywords, and `:nix/path` / `:nix/expr` are emitted as they are.
//! Keys are SORTED, because an Erlang map has no insertion order to preserve
//! and a generator whose output is a function of map internals is not one
//! anybody can diff. A caller who needs the author's order edits the TREE,
//! where the order is the document's.

use rnix::ast::{self, AstToken, HasEntry, InterpolPart, LiteralKind, UnaryOpKind};
use rnix::{SyntaxKind, SyntaxNode};
use rowan::ast::AstNode;
use rustler::types::map::MapIterator;
use rustler::types::tuple::get_tuple;
use rustler::types::atom::Atom;
use rustler::{Encoder, Env, NifResult, Term, TermType};

use crate::tree;
use crate::{atom, error_reply, make_binary, make_vector, ok_reply, opt_atom, refusal};

// ══ projection ══════════════════════════════════════════════════════════════

/// Why a value was refused, in the terms the caller has: what the node IS
/// (`:kind`), where it starts (`:where`), and enough of it to recognise
/// (`:text`). The MESSAGE stays one line and stays factual; what to do about a
/// refusal is policy, and policy lives in `priv/lib/nix.bl`.
struct Refused {
    message: String,
    kind: Option<SyntaxKind>,
    /// `None` unless the projection was given a WHOLE document.
    ///
    /// A position is only meaningful against the text it indexes, and a subtree
    /// carries only its own — so a refusal from `(nix/data (nix/get doc path))`
    /// would report the fragment's line 1, which reads as the FILE's line 1 and
    /// sends a caller to the wrong line. A position that means something else is
    /// worse than no position, so this is right or it is absent.
    offset: Option<usize>,
    text: String,
}

#[derive(Clone, Copy, PartialEq)]
enum KeyMode {
    /// The default. A Nix attribute name is arbitrary text — `"foo bar"` is a
    /// legal one — and a string is the one key type that can hold it.
    String,
    /// Interns an atom per attribute, and the atom table is bounded and never
    /// collected: a `.nix` file from anywhere is a way to exhaust it. Opt-in,
    /// exactly as `bl.json`'s `:keys :keyword` is.
    Keyword,
    /// Interns nothing and refuses an unknown name. The mode for a caller who
    /// wants `:keyword`'s ergonomics on a document it does not trust.
    Existing,
}

#[derive(Clone, Copy, PartialEq)]
enum Unsupported {
    Throw,
    Tag,
}

struct Ctx<'a, 's> {
    env: Env<'a>,
    key_mode: KeyMode,
    unsupported: Unsupported,
    src: &'s str,
    struct_k: Atom,
    items_k: Atom,
    vec_mod: Atom,
    tag_expr: Atom,
    tag_path: Atom,
}

/// How much of a refused node to quote back. Enough to recognise, short enough
/// that one pathological line cannot become the whole error.
const EXCERPT: usize = 160;

impl<'a, 's> Ctx<'a, 's> {
    fn refuse(&self, node: &SyntaxNode, why: &str) -> Refused {
        let range = node.text_range();
        let start = usize::from(range.start());
        let end = usize::from(range.end()).min(self.src.len());
        let text = &self.src[start..end];
        let mut excerpt: String = text.chars().take(EXCERPT).collect();
        if excerpt.len() < text.len() {
            excerpt.push('…');
        }
        Refused {
            message: why.to_string(),
            kind: Some(node.kind()),
            offset: Some(start),
            text: excerpt,
        }
    }

    /// `{:nix/expr "…"}` — the node's own source, claimed to be nothing.
    fn tag(&self, node: &SyntaxNode) -> Term<'a> {
        let text = node.to_string();
        let t = crate::make_binary(self.env, text.as_bytes()).unwrap_or_else(|_| {
            self.tag_expr.to_term(self.env)
        });
        Term::map_from_term_arrays(self.env, &[self.tag_expr.to_term(self.env)], &[t])
            .unwrap_or_else(|_| self.tag_expr.to_term(self.env))
    }

    fn tags_expr(&self) -> bool {
        self.unsupported == Unsupported::Tag
    }

    // ── the value view ──────────────────────────────────────────────────────

    /// Project a node: the root of a document, or any expression beneath it.
    ///
    /// Only expressions. A caller that has navigated to a binding
    /// (`nixpkgs.url = "…";`) is holding an `NODE_ATTRPATH_VALUE`, and the
    /// refusal names that kind rather than guessing which half was meant.
    fn value(&self, node: &SyntaxNode) -> Result<Term<'a>, Refused> {
        if node.kind() == SyntaxKind::NODE_ROOT {
            let root = ast::Root::cast(node.clone())
                .ok_or_else(|| self.refuse(node, "this is not a Nix document"))?;
            let expr = root
                .expr()
                .ok_or_else(|| self.refuse(node, "this document is empty"))?;
            return self.expr(&expr);
        }
        match ast::Expr::cast(node.clone()) {
            Some(expr) => self.expr(&expr),
            None if self.tags_expr() => Ok(self.tag(node)),
            None => Err(self.refuse(
                node,
                "this node is not an expression, so it has no value of its own",
            )),
        }
    }

    /// An expression as data, or as `{:nix/expr …}`.
    ///
    /// THIS is where `:unsupported :tag` is implemented, and at this level
    /// rather than at the top of the call: a refusal belongs to the node that
    /// caused it, so the surrounding document keeps its shape and only the
    /// unrepresentable part becomes text. Tagging the whole document because
    /// one binding held a lambda would make the projection useless exactly
    /// where it is most wanted.
    ///
    /// An error that SURVIVES to here is a refusal about this node (a child's
    /// refusal was already handled, one level down), so the tag is always the
    /// right answer — and a refusal that has no value-shaped hole to sit in
    /// (an `inherit`, a duplicated attribute) arrives from the attrset's own
    /// projection and tags the ATTRSET, which is the nearest node that can
    /// hold it.
    fn expr(&self, expr: &ast::Expr) -> Result<Term<'a>, Refused> {
        match self.project(expr) {
            Ok(value) => Ok(value),
            Err(why) if self.tags_expr() => {
                let _ = why;
                Ok(self.tag(expr.syntax()))
            }
            Err(why) => Err(why),
        }
    }

    fn project(&self, expr: &ast::Expr) -> Result<Term<'a>, Refused> {
        match expr {
            ast::Expr::AttrSet(a) => self.attrset(a),
            ast::Expr::List(l) => self.list(l),
            ast::Expr::Str(s) => self.string(s),
            ast::Expr::Literal(l) => self.literal(l),
            ast::Expr::Ident(i) => self.ident(i),
            ast::Expr::Paren(p) => match p.expr() {
                Some(inner) => self.expr(&inner),
                None => Err(self.refuse(p.syntax(), "empty parentheses")),
            },
            ast::Expr::PathAbs(p) => self.path(p.syntax(), p.parts()),
            ast::Expr::PathRel(p) => self.path(p.syntax(), p.parts()),
            ast::Expr::PathHome(p) => self.path(p.syntax(), p.parts()),
            ast::Expr::PathSearch(p) => self.path_search(p),
            ast::Expr::UnaryOp(u) => self.unary(u),
            other => Err(self.refuse(other.syntax(), UNSUPPORTED)),
        }
    }

    fn attrset(&self, set: &ast::AttrSet) -> Result<Term<'a>, Refused> {
        if set.rec_token().is_some() {
            return Err(self.refuse(
                set.syntax(),
                "a `rec` attrset projects to a plain map, which is not what it means",
            ));
        }
        let mut knot: Vec<(String, Knot<'a>)> = Vec::new();
        for entry in set.entries() {
            match entry {
                ast::Entry::AttrpathValue(pair) => {
                    let path = self.attrpath(&pair)?;
                    let value = match pair.value() {
                        Some(v) => self.expr(&v)?,
                        None => {
                            return Err(self.refuse(pair.syntax(), "this binding has no value"))
                        }
                    };
                    insert(&mut knot, &path, Knot::Val(value), self, pair.syntax())?;
                }
                ast::Entry::Inherit(i) => {
                    return Err(self.refuse(
                        i.syntax(),
                        "`inherit` names a variable in scope, not a value",
                    ))
                }
            }
        }
        self.knot_map(knot)
    }

    fn attrpath(&self, pair: &ast::AttrpathValue) -> Result<Vec<String>, Refused> {
        let path = pair
            .attrpath()
            .ok_or_else(|| self.refuse(pair.syntax(), "this binding has no name"))?;
        let mut names = Vec::new();
        for attr in path.attrs() {
            names.push(self.attr_name(&attr)?);
        }
        if names.is_empty() {
            return Err(self.refuse(path.syntax(), "this binding has no name"));
        }
        Ok(names)
    }

    fn attr_name(&self, attr: &ast::Attr) -> Result<String, Refused> {
        match attr {
            ast::Attr::Ident(i) => Ok(i.syntax().to_string()),
            ast::Attr::Str(s) => {
                let mut it = s.normalized_parts().into_iter();
                match (it.next(), it.next()) {
                    (Some(InterpolPart::Literal(text)), None) => Ok(text),
                    _ => Err(self.refuse(
                        s.syntax(),
                        "this attribute name is computed, so it has no fixed name",
                    )),
                }
            }
            ast::Attr::Dynamic(d) => Err(self.refuse(
                d.syntax(),
                "this attribute name is computed, so it has no fixed name",
            )),
        }
    }

    fn list(&self, list: &ast::List) -> Result<Term<'a>, Refused> {
        let mut items = Vec::new();
        for item in list.items() {
            items.push(self.expr(&item)?);
        }
        make_vector(
            self.env,
            items,
            self.struct_k,
            self.items_k,
            self.vec_mod,
        )
        .map_err(|e| self.refuse(list.syntax(), &format!("{e:?}")))
    }

    fn string(&self, s: &ast::Str) -> Result<Term<'a>, Refused> {
        let mut text = String::new();
        for part in s.normalized_parts() {
            match part {
                InterpolPart::Literal(t) => text.push_str(&t),
                InterpolPart::Interpolation(i) => {
                    return Err(self.refuse(
                        i.syntax(),
                        "this string interpolates an expression, so its text is not known yet",
                    ))
                }
            }
        }
        make_binary(self.env, text.as_bytes())
            .map_err(|e| self.refuse(s.syntax(), &format!("{e:?}")))
    }

    fn literal(&self, l: &ast::Literal) -> Result<Term<'a>, Refused> {
        match l.kind() {
            LiteralKind::Integer(i) => match i.value() {
                Ok(n) => Ok(n.encode(self.env)),
                Err(_) => Err(self.refuse(l.syntax(), "this integer does not fit")),
            },
            LiteralKind::Float(f) => match f.value() {
                Ok(n) => Ok(n.encode(self.env)),
                Err(_) => Err(self.refuse(l.syntax(), "this float does not parse")),
            },
            // Nix evaluates a bare URI to a string, so this is what the value
            // IS rather than a convenience: `https://x` == "https://x".
            LiteralKind::Uri(u) => make_binary(self.env, u.syntax().text().as_bytes())
                .map_err(|e| self.refuse(l.syntax(), &format!("{e:?}"))),
        }
    }

    fn ident(&self, i: &ast::Ident) -> Result<Term<'a>, Refused> {
        let name = i.syntax().to_string();
        match name.as_str() {
            "true" => Ok(self.true_atom().to_term(self.env)),
            "false" => Ok(self.false_atom().to_term(self.env)),
            "null" => Ok(self.nil_atom().to_term(self.env)),
            _ => Err(self.refuse(
                i.syntax(),
                "this is a variable reference, so its value is not in the text",
            )),
        }
    }

    fn true_atom(&self) -> Atom {
        crate::atom(self.env, "true").unwrap_or(self.tag_expr)
    }
    fn false_atom(&self) -> Atom {
        crate::atom(self.env, "false").unwrap_or(self.tag_expr)
    }
    fn nil_atom(&self) -> Atom {
        crate::atom(self.env, "nil").unwrap_or(self.tag_expr)
    }

    /// A path literal, or a refusal when it interpolates — `${}` inside a path
    /// is a computation like any other.
    fn path(
        &self,
        node: &SyntaxNode,
        parts: Vec<InterpolPart<ast::PathContent>>,
    ) -> Result<Term<'a>, Refused> {
        let mut text = String::new();
        for part in parts {
            match part {
                InterpolPart::Literal(c) => text.push_str(&c.text().to_string()),
                InterpolPart::Interpolation(i) => return Err(self.refuse(i.syntax(), INTERPOLATED)),
            }
        }
        self.path_text(node, text)
    }

    /// A search path (`<nixpkgs>`) is a single opaque token and cannot
    /// interpolate, so it needs no folding.
    fn path_search(&self, p: &ast::PathSearch) -> Result<Term<'a>, Refused> {
        self.path_text(p.syntax(), p.syntax().to_string())
    }

    /// A path crosses as `{:nix/path "…"}`: a NAMESPACED KEYWORD, so a real
    /// map that happens to hold a key called "nix/path" can never be confused
    /// with one.
    fn path_text(&self, node: &SyntaxNode, text: String) -> Result<Term<'a>, Refused> {
        let value = make_binary(self.env, text.as_bytes())
            .map_err(|e| self.refuse(node, &format!("{e:?}")))?;
        Term::map_from_term_arrays(self.env, &[self.tag_path.to_term(self.env)], &[value])
            .map_err(|_| self.refuse(node, "could not build the path tag"))
    }

    /// `-1` is a unary minus applied to `1`, not a literal, so the one unary
    /// operation Nix has that produces a VALUE has to be folded back. `!x` is
    /// a computation and is refused with the rest.
    fn unary(&self, u: &ast::UnaryOp) -> Result<Term<'a>, Refused> {
        if u.operator() != Some(UnaryOpKind::Negate) {
            return Err(self.refuse(u.syntax(), UNSUPPORTED));
        }
        match u.expr() {
            Some(ast::Expr::Literal(l)) => match l.kind() {
                LiteralKind::Integer(i) => i
                    .value()
                    .map(|n| (-n).encode(self.env))
                    .map_err(|_| self.refuse(u.syntax(), "this integer does not fit")),
                LiteralKind::Float(f) => f
                    .value()
                    .map(|n| (-n).encode(self.env))
                    .map_err(|_| self.refuse(u.syntax(), "this float does not parse")),
                LiteralKind::Uri(_) => Err(self.refuse(u.syntax(), UNSUPPORTED)),
            },
            _ => Err(self.refuse(u.syntax(), UNSUPPORTED)),
        }
    }

    // ── building the map ────────────────────────────────────────────────────

    fn key(&self, name: &str) -> Result<Term<'a>, Refused> {
        match self.key_mode {
            KeyMode::String => make_binary(self.env, name.as_bytes())
                .map_err(|e| self.refuse_key(name, &format!("{e:?}"))),
            KeyMode::Keyword => Atom::from_str(self.env, name)
                .map(|a| a.to_term(self.env))
                .map_err(|_| self.refuse_key(name, "the atom table is full")),
            KeyMode::Existing => Atom::existing_from_str(self.env, name)
                .map(|a| a.to_term(self.env))
                .map_err(|_| self.refuse_key(name, "this name is not an existing atom")),
        }
    }

    fn refuse_key(&self, name: &str, why: &str) -> Refused {
        Refused {
            message: format!("attribute {name:?} cannot be a key: {why}"),
            kind: None,
            offset: None,
            text: name.to_string(),
        }
    }

    fn knot_map(&self, knot: Vec<(String, Knot<'a>)>) -> Result<Term<'a>, Refused> {
        let mut keys: Vec<Term<'a>> = Vec::with_capacity(knot.len());
        let mut vals: Vec<Term<'a>> = Vec::with_capacity(knot.len());
        for (name, value) in knot {
            keys.push(self.key(&name)?);
            vals.push(match value {
                Knot::Val(t) => t,
                Knot::Map(inner) => self.knot_map(inner)?,
            });
        }
        Term::map_from_term_arrays(self.env, &keys, &vals)
            .map_err(|_| self.refuse_key("", "could not build the map"))
    }
}

/// The one-line summary every unsupported node gets. The KIND is in `:kind`,
/// so the message does not repeat it — it says what class of thing this is.
const UNSUPPORTED: &str =
    "this expression computes a value, so the text alone does not contain it";

/// What an interpolated string or path is refused with. Its own line, because
/// it is the one refusal a caller meets constantly in real configuration.
const INTERPOLATED: &str =
    "this interpolates an expression, so its text is not known yet";

/// Nix's attribute STACK. `a.b.c = 1;` is one binding with a three-name path,
/// and it has to become three nested maps — MERGED with any sibling that
/// already opened one of those levels, because `{ a.b = 1; a.c = 2; }` is
/// legal Nix and common.
enum Knot<'a> {
    Map(Vec<(String, Knot<'a>)>),
    Val(Term<'a>),
}

fn insert<'a>(
    into: &mut Vec<(String, Knot<'a>)>,
    path: &[String],
    value: Knot<'a>,
    cx: &Ctx<'a, '_>,
    node: &SyntaxNode,
) -> Result<(), Refused> {
    let (name, rest) = match path.split_first() {
        Some(pair) => pair,
        None => return Err(cx.refuse(node, "this binding has no name")),
    };
    if rest.is_empty() {
        if into.iter().any(|(k, _)| k == name) {
            return Err(cx.refuse(node, "this attribute is defined twice"));
        }
        into.push((name.clone(), value));
        return Ok(());
    }
    match into.iter_mut().find(|(k, _)| k == name) {
        None => {
            let mut inner: Vec<(String, Knot<'a>)> = Vec::new();
            insert(&mut inner, rest, value, cx, node)?;
            into.push((name.clone(), Knot::Map(inner)));
            Ok(())
        }
        Some((_, Knot::Map(inner))) => insert(inner, rest, value, cx, node),
        Some(_) => Err(cx.refuse(
            node,
            "this attribute is a value and an attrset at once",
        )),
    }
}

/// The NIF body. `nix_data`.
pub fn project<'a>(env: Env<'a>, node: Term<'a>, opts: Term<'a>) -> NifResult<Term<'a>> {
    let key_mode = match opt_atom(env, opts, "keys", "string").as_str() {
        "keyword" => KeyMode::Keyword,
        // The atom's NAME is the keyword without its colon, so a hyphenated
        // keyword is hyphenated here. `existing_atom` — the Rust spelling —
        // would silently fall through to the default, which is a mode the
        // caller did not ask for and would never see fail.
        "existing-atom" => KeyMode::Existing,
        _ => KeyMode::String,
    };
    let unsupported = match opt_atom(env, opts, "unsupported", "throw").as_str() {
        "tag" => Unsupported::Tag,
        _ => Unsupported::Throw,
    };

    let green = match tree::from_term(node) {
        Ok(g) => g,
        Err(reason) => {
            let detail = refusal(env, &reason, "", None, vec![])?;
            return error_reply(env, detail);
        }
    };
    let syntax = SyntaxNode::new_root(green);
    let whole_document = syntax.kind() == SyntaxKind::NODE_ROOT;
    // The source is the tree's own text: the tree is lossless, so this is the
    // document the caller parsed, and an offset into it is an offset a caller
    // can act on.
    let src = syntax.to_string();
    let cx = Ctx {
        env,
        key_mode,
        unsupported,
        src: &src,
        struct_k: atom(env, "__struct__")?,
        items_k: atom(env, "items")?,
        vec_mod: atom(env, "Elixir.BeamLisp.Vector")?,
        tag_expr: atom(env, "nix/expr")?,
        tag_path: atom(env, "nix/path")?,
    };

    match cx.value(&syntax) {
        Ok(value) => ok_reply(env, value),
        Err(r) => {
            let mut extra: Vec<(&str, Term<'a>)> = Vec::new();
            if let Some(kind) = r.kind {
                extra.push((
                    "kind",
                    atom(env, &tree::kind_name(kind))?.to_term(env),
                ));
            }
            extra.push(("text", make_binary(env, r.text.as_bytes())?));
            let at = if whole_document { r.offset } else { None };
            error_reply(
                env,
                refusal(env, &r.message, &src, at, vec![
                    ("reason", atom(env, "unsupported")?.to_term(env)),
                ].into_iter().chain(extra).collect())?,
            )
        }
    }
}

// ══ generation ══════════════════════════════════════════════════════════════
//
// The inverse. Where the projection stops at what the text SAYS, this decides
// what the text will BE: key order, indentation, quoting, escaping. Those are
// choices, they are made once, here, and they are documented at the top.

/// A refusal from the generator, addressed the way the input was written.
#[derive(Clone)]
enum Step {
    Key(String),
    Index(usize),
}

struct NoSpelling {
    message: String,
    path: Vec<Step>,
}

struct Gen<'a> {
    env: Env<'a>,
    indent: usize,
    struct_k: Atom,
    items_k: Atom,
    vec_mod: Atom,
    tag_expr: Atom,
    tag_path: Atom,
}

impl<'a> Gen<'a> {
    fn spell(&self, path: &[Step]) -> String {
        let mut out = String::new();
        for step in path {
            match step {
                Step::Key(k) => {
                    if !out.is_empty() {
                        out.push('.');
                    }
                    out.push_str(k);
                }
                Step::Index(i) => {
                    out.push('[');
                    out.push_str(&i.to_string());
                    out.push(']');
                }
            }
        }
        out
    }

    fn write(&self, out: &mut String, depth: usize, path: &[Step], t: Term<'a>) -> Result<(), NoSpelling> {
        if t.is_map() {
            return self.map(out, depth, path, t);
        }
        if t.is_list() {
            let items = t
                .decode::<Vec<Term>>()
                .map_err(|_| self.no(path, "a list that cannot be read"))?;
            return self.list(out, depth, path, items);
        }
        if let Ok(text) = t.decode::<rustler::Binary>() {
            out.push('"');
            escape(out, std::str::from_utf8(text.as_slice()).unwrap_or_default());
            out.push('"');
            return Ok(());
        }
        if let Ok(n) = t.decode::<i64>() {
            out.push_str(&n.to_string());
            return Ok(());
        }
        if let Ok(f) = t.decode::<f64>() {
            // Nix has no NaN and no infinity, and `NaN` in a Nix file would
            // parse as a VARIABLE — so an unwritable number must not be
            // written as something else.
            if !f.is_finite() {
                return Err(self.no(path, "a non-finite float has no Nix spelling"));
            }
            // `{:?}` is shortest-round-trip and always keeps the fractional
            // part — `2.0` prints as `2.0`, never `2`. That matters here and
            // nowhere else: in Nix `2` is an integer, and dropping the point
            // would change the value.
            out.push_str(&format!("{f:?}"));
            return Ok(());
        }
        if let Ok(a) = t.atom_to_string() {
            match a.as_str() {
                "true" | "false" => out.push_str(&a),
                // `nil` is the beam-lisp spelling of Nix's null; `null` is
                // accepted too, so a map that came from JSON or from this
                // crate's own projection round-trips without a rename.
                "nil" | "null" => out.push_str("null"),
                _ => return Err(self.no(path, &format!("a keyword (:{a}) has no Nix spelling"))),
            }
            return Ok(());
        }
        Err(self.no(path, &format!("a {} has no Nix spelling", type_name(t))))
    }

    fn no(&self, path: &[Step], why: &str) -> NoSpelling {
        let _ = self.env;
        NoSpelling {
            message: format!("{why} at `{}`", self.spell(path)),
            path: path.iter().map(clone_step).collect(),
        }
    }

    /// A map: a tag, a Vector, or an attrset.
    fn map(&self, out: &mut String, depth: usize, path: &[Step], t: Term<'a>) -> Result<(), NoSpelling> {
        // A Vector IS a map (a struct tag plus a tuple), so it is recognised
        // first — and by the tag, not by a key of the right name, so a plain
        // map with an `items` key is not mistaken for one.
        if let Ok(tag) = t.map_get(self.struct_k) {
            if tag == self.vec_mod.to_term(self.env) {
                let items = t
                    .map_get(self.items_k)
                    .and_then(|i| get_tuple(i).map_err(|_| rustler::Error::BadArg))
                    .map(|items| items.to_vec())
                    .map_err(|_| self.no(path, "a Vector whose items are not a tuple"))?;
                return self.list(out, depth, path, items);
            }
        }
        // `{:nix/expr "…"}` and `{:nix/path "…"}` — reserved, but only as
        // EXACTLY a one-key map, so a real map that happens to carry the key
        // alongside others is still a map.
        if let Some((key, value)) = single_entry(t) {
            if let Ok(name) = key.decode::<Atom>() {
                if name == self.tag_expr {
                    let text = value
                        .decode::<rustler::Binary>()
                        .map_err(|_| self.no(path, ":nix/expr must hold a string"))?;
                    // Parenthesised, so it is legal in ANY expression position,
                    // a binding's value included.
                    out.push('(');
                    out.push_str(std::str::from_utf8(text.as_slice()).unwrap_or_default());
                    out.push(')');
                    return Ok(());
                }
                if name == self.tag_path {
                    let text = value
                        .decode::<rustler::Binary>()
                        .map_err(|_| self.no(path, ":nix/path must hold a string"))?;
                    out.push_str(std::str::from_utf8(text.as_slice()).unwrap_or_default());
                    return Ok(());
                }
            }
        }
        self.attrset(out, depth, path, t)
    }

    fn attrset(&self, out: &mut String, depth: usize, path: &[Step], t: Term<'a>) -> Result<(), NoSpelling> {
        let mut pairs: Vec<(String, Term<'a>)> = Vec::new();
        for (k, v) in MapIterator::new(t).ok_or_else(|| self.no(path, "a map that cannot be read"))? {
            let name = key_name(&k).ok_or_else(|| {
                self.no(path, "an attribute whose key is neither a string nor a keyword")
            })?;
            pairs.push((name, v));
        }
        if pairs.is_empty() {
            out.push_str("{ }");
            return Ok(());
        }
        // Sorted by name, because the map has no order of its own to keep: an
        // Erlang map iterates in term order, which is a function of the atom
        // table and of nothing the caller wrote. A generator's output has to be
        // a function of its INPUT.
        pairs.sort_by(|a, b| a.0.cmp(&b.0));
        out.push_str("{\n");
        for (name, value) in pairs {
            push_indent(out, depth + 1, self.indent);
            out.push_str(&attr_name(&name));
            out.push_str(" = ");
            let mut child = path.to_vec();
            child.push(Step::Key(name));
            self.write(out, depth + 1, &child, value)?;
            out.push_str(";\n");
        }
        push_indent(out, depth, self.indent);
        out.push('}');
        Ok(())
    }

    fn list(&self, out: &mut String, depth: usize, path: &[Step], items: Vec<Term<'a>>) -> Result<(), NoSpelling> {
        if items.is_empty() {
            out.push_str("[ ]");
            return Ok(());
        }
        let mut parts: Vec<String> = Vec::with_capacity(items.len());
        for (i, item) in items.iter().enumerate() {
            let mut child = path.to_vec();
            child.push(Step::Index(i));
            let mut one = String::new();
            self.write(&mut one, depth + 1, &child, *item)?;
            // A LIST ELEMENT IS NOT A FULL EXPRESSION in Nix: the grammar puts
            // `expr_select` between the brackets, and a unary minus is above
            // it. So `[ -3 ]` is a syntax error and `[ (-3) ]` is not — found by
            // the fixed-point law, which is exactly what it is for, since the
            // generator had no reason to know it otherwise. A NEGATIVE NUMBER is
            // the only shape this generator can put in a list that needs this:
            // every other value it emits is select-level already, and a
            // `{:nix/expr …}` arrives parenthesised.
            if negative(&item) {
                one = format!("({one})");
            }
            parts.push(one);
        }
        // One line when every element is one line, which is what a human writes
        // for `[ "a" "b" ]` and never for a list of attrsets.
        if parts.iter().all(|p| !p.contains('\n')) {
            out.push_str("[ ");
            out.push_str(&parts.join(" "));
            out.push_str(" ]");
            return Ok(());
        }
        out.push_str("[\n");
        for part in parts {
            push_indent(out, depth + 1, self.indent);
            out.push_str(&part);
            out.push('\n');
        }
        push_indent(out, depth, self.indent);
        out.push(']');
        Ok(())
    }
}

/// Is this value a number that renders with a leading `-`?
///
/// `is_sign_negative` and not `< 0.0`, so `-0.0` is covered: it renders as
/// `-0.0`, and `[ -0.0 ]` is a syntax error for the same reason `[ -3 ]` is.
fn negative(t: &Term) -> bool {
    if let Ok(n) = t.decode::<i64>() {
        return n < 0;
    }
    if let Ok(f) = t.decode::<f64>() {
        return f.is_sign_negative();
    }
    false
}

fn clone_step(s: &Step) -> Step {
    match s {
        Step::Key(k) => Step::Key(k.clone()),
        Step::Index(i) => Step::Index(*i),
    }
}

fn single_entry<'a>(t: Term<'a>) -> Option<(Term<'a>, Term<'a>)> {
    let mut it = MapIterator::new(t)?;
    let first = it.next()?;
    if it.next().is_some() {
        return None;
    }
    Some(first)
}

fn key_name(t: &Term) -> Option<String> {
    if let Ok(name) = t.atom_to_string() {
        return Some(name);
    }
    t.decode::<rustler::Binary>()
        .ok()
        .map(|b| String::from_utf8_lossy(b.as_slice()).into_owned())
}

fn type_name(t: Term) -> &'static str {
    match t.get_type() {
        TermType::Atom => "keyword",
        TermType::Binary => "string",
        TermType::List => "list",
        TermType::Float => "float",
        TermType::Fun => "function",
        TermType::Integer => "integer",
        TermType::Map => "map",
        TermType::Pid => "process",
        TermType::Port => "port",
        TermType::Ref => "reference",
        TermType::Tuple => "tuple",
        TermType::Unknown => "value",
    }
}

fn push_indent(out: &mut String, depth: usize, indent: usize) {
    for _ in 0..depth * indent {
        out.push(' ');
    }
}

/// A double-quoted Nix string's body.
///
/// `\${` is the one escape a reader has to know about: Nix interpolates on the
/// two-character sequence `${`, so a literal one is spelled with a backslash.
/// Emitting `${` unescaped would turn a plain string into an expression.
fn escape(out: &mut String, text: &str) {
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '\\' => out.push_str("\\\\"),
            '"' => out.push_str("\\\""),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '$' if chars.peek() == Some(&'{') => out.push_str("\\$"),
            other => out.push(other),
        }
    }
}

/// A Nix keyword cannot be a bare attribute name, and neither can a name that
/// is not an identifier. Everything else is written as it was.
const KEYWORDS: [&str; 9] = [
    "if", "then", "else", "assert", "with", "let", "in", "rec", "inherit",
];

fn attr_name(name: &str) -> String {
    let bare = !name.is_empty()
        && !KEYWORDS.contains(&name)
        && name
            .chars()
            .enumerate()
            .all(|(i, c)| match c {
                'a'..='z' | 'A'..='Z' | '_' => true,
                '0'..='9' | '-' | '\'' => i > 0,
                _ => false,
            });
    if bare {
        name.to_string()
    } else {
        let mut out = String::with_capacity(name.len() + 2);
        out.push('"');
        escape(&mut out, name);
        out.push('"');
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_bare_name_is_written_bare() {
        assert_eq!(attr_name("description"), "description");
        assert_eq!(attr_name("nixos-unstable"), "nixos-unstable");
        assert_eq!(attr_name("_private"), "_private");
        assert_eq!(attr_name("state-directory"), "state-directory");
    }

    /// `isSystemUser` may not lead with a digit, a keyword may not be bare at
    /// all, and an empty name has to be quoted to exist.
    #[test]
    fn a_name_that_is_not_an_identifier_is_quoted() {
        assert_eq!(attr_name("9lives"), "\"9lives\"");
        assert_eq!(attr_name("a b"), "\"a b\"");
        assert_eq!(attr_name("if"), "\"if\"");
        assert_eq!(attr_name("inherit"), "\"inherit\"");
        assert_eq!(attr_name(""), "\"\"");
        assert_eq!(attr_name("a.b"), "\"a.b\"");
    }

    /// `true`, `false` and `null` are IDENTIFIERS in Nix, not keywords, so a
    /// binding may be called `true` without quoting.
    #[test]
    fn the_literal_names_are_ordinary_identifiers() {
        assert_eq!(attr_name("true"), "true");
        assert_eq!(attr_name("null"), "null");
    }

    /// The escape that matters: `${` opens an interpolation, so a literal one
    /// must be spelled `\${` or a string becomes an expression.
    #[test]
    fn escapes() {
        let mut out = String::new();
        escape(&mut out, "a${b}");
        assert_eq!(out, "a\\${b}");
        out.clear();
        escape(&mut out, "line\nquote\"back\\slash");
        assert_eq!(out, "line\\nquote\\\"back\\\\slash");
        out.clear();
        escape(&mut out, "${}");
        assert_eq!(out, "\\${}");
    }

    /// A quoted attribute name escapes the same way a string does, because
    /// that is exactly what it is.
    #[test]
    fn a_quoted_name_escapes_like_a_string() {
        assert_eq!(attr_name("a\"b"), "\"a\\\"b\"");
    }
}
/// The NIF body. `nix_emit`.
pub fn generate<'a>(env: Env<'a>, value: Term<'a>, opts: Term<'a>) -> NifResult<Term<'a>> {
    let indent = match opts
        .map_get(atom(env, "indent")?)
        .and_then(|t| t.decode::<i64>())
    {
        Ok(n) if (0..=16).contains(&n) => n as usize,
        _ => 2,
    };
    let gen = Gen {
        env,
        indent,
        struct_k: atom(env, "__struct__")?,
        items_k: atom(env, "items")?,
        vec_mod: atom(env, "Elixir.BeamLisp.Vector")?,
        tag_expr: atom(env, "nix/expr")?,
        tag_path: atom(env, "nix/path")?,
    };
    let mut out = String::new();
    match gen.write(&mut out, 0, &[], value) {
        Ok(()) => ok_reply(env, make_binary(env, out.as_bytes())?),
        Err(e) => {
            // The path is a VECTOR, not a list: it is an address, and every
            // address this API takes and returns is a vector.
            let path: Vec<Term<'a>> = e
                .path
                .iter()
                .map(|s| match s {
                    Step::Key(k) => make_binary(env, k.as_bytes()),
                    Step::Index(i) => Ok((*i).encode(env)),
                })
                .collect::<NifResult<Vec<Term>>>()?;
            let path = make_vector(env, path, gen.struct_k, gen.items_k, gen.vec_mod)?;
            let detail = refusal(env, &e.message, "", None, vec![
                ("reason", atom(env, "unrepresentable")?.to_term(env)),
                ("path", path),
            ])?;
            error_reply(env, detail)
        }
    }
}
