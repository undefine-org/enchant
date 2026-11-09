use eetf::{Atom, BigInteger, Binary, List, Map, Term, Tuple};
use num_bigint::BigInt;
use std::collections::HashMap;

pub const MAX_PACKET: usize = 1_048_576;
pub type Result<T> = std::result::Result<T, String>;

pub fn atom(name: &str) -> Term { Atom::from(name).into() }
pub fn binary(text: &str) -> Term { Binary::from(text.as_bytes().to_vec()).into() }
pub fn integer(value: impl Into<BigInt>) -> Term { BigInteger { value: value.into() }.into() }
pub fn list(elements: Vec<Term>) -> Term { List::from(elements).into() }
pub fn tuple(elements: Vec<Term>) -> Term { Tuple::from(elements).into() }
pub fn map(entries: Vec<(&str, Term)>) -> Term {
    Map::from(entries.into_iter().map(|(k,v)| (atom(k),v)).collect::<HashMap<_,_>>()).into()
}
pub fn ok() -> Term { map(vec![("ok", atom("true"))]) }
pub fn error(message: &str) -> Term {
    map(vec![("ok", atom("false")), ("status", atom("error")), ("error", binary(message))])
}
pub fn items(term: &Term) -> Result<&[Term]> {
    match term { Term::List(l) => Ok(&l.elements), _ => Err("expected a proper list".into()) }
}
pub fn fields(term: &Term) -> Result<&[Term]> {
    match term { Term::Tuple(t) => Ok(&t.elements), _ => Err("expected a request tuple".into()) }
}
pub fn text(term: &Term) -> Result<&str> {
    match term {
        Term::Binary(b) => std::str::from_utf8(&b.bytes).map_err(|_| "expected UTF-8".into()),
        Term::Atom(a) => Ok(&a.name),
        _ => Err("expected a binary or atom".into()),
    }
}
pub fn symbol(term: &Term) -> Result<&str> {
    let parts = fields(term)?;
    if parts.len() == 2 && text(&parts[0])? == "symbol" { text(&parts[1]) }
    else { Err("expected a tagged symbol".into()) }
}
pub fn number(term: &Term) -> Result<BigInt> {
    match term {
        Term::FixInteger(n) => Ok(n.value.into()),
        Term::BigInteger(n) => Ok(n.value.clone()),
        _ => Err("expected an integer".into()),
    }
}
