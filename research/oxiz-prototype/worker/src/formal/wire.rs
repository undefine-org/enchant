use eetf::{Atom, BigInteger, Binary, FixInteger, List, Map, Term};
use num_bigint::BigInt;
use num_traits::ToPrimitive;
use std::borrow::Cow;
use std::collections::HashMap;

pub const MAX_PACKET: usize = 1_048_576;
pub type Result<T> = std::result::Result<T, Fault>;

#[derive(Clone, Debug)]
pub struct Fault {
    pub kind: &'static str,
    pub message: String,
}

impl Fault {
    pub fn invalid(message: impl Into<String>) -> Self {
        Self { kind: "invalid", message: message.into() }
    }
    pub fn unsupported(message: impl Into<String>) -> Self {
        Self { kind: "unsupported", message: message.into() }
    }
    pub fn backend(message: impl Into<String>) -> Self {
        Self { kind: "error", message: message.into() }
    }
}

impl std::fmt::Display for Fault {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}: {}", self.kind, self.message)
    }
}
impl std::error::Error for Fault {}

pub fn atom(value: &str) -> Term { Atom::from(value).into() }
pub fn binary(value: &str) -> Term { Binary::from(value.as_bytes().to_vec()).into() }
pub fn integer(value: impl Into<BigInt>) -> Term { BigInteger { value: value.into() }.into() }
pub fn list(values: impl IntoIterator<Item = Term>) -> Term {
    List::from(values.into_iter().collect::<Vec<_>>()).into()
}
pub fn map(values: impl IntoIterator<Item = (&'static str, Term)>) -> Term {
    Map::from(values.into_iter().map(|(k, v)| (atom(k), v)).collect::<HashMap<_, _>>()).into()
}
pub fn binary_map(values: impl IntoIterator<Item = (&'static str, Term)>) -> Term {
    Map::from(values.into_iter().map(|(k, v)| (binary(k), v)).collect::<HashMap<_, _>>()).into()
}
pub fn tagged(tag: &str, values: impl IntoIterator<Item = Term>) -> Term {
    list(std::iter::once(binary(tag)).chain(values))
}
pub fn text(value: &Term) -> Result<&str> {
    match value {
        Term::Binary(value) => std::str::from_utf8(&value.bytes)
            .map_err(|_| Fault::invalid("expected a UTF-8 binary")),
        Term::Atom(value) => Ok(&value.name),
        _ => Err(Fault::invalid("expected a binary or fixed protocol atom")),
    }
}
pub fn binary_text(value: &Term) -> Result<&str> {
    if !matches!(value, Term::Binary(_)) {
        return Err(Fault::invalid("dynamic names, sorts and operators must be binaries"));
    }
    text(value)
}
pub fn items(value: &Term) -> Result<Cow<'_, [Term]>> {
    match value {
        Term::List(value) => Ok(Cow::Borrowed(&value.elements)),
        // Erlang encodes a proper list of small integers as STRING_EXT.
        Term::ByteList(value) => Ok(Cow::Owned(value.bytes.iter()
            .map(|n| Term::from(FixInteger { value: i32::from(*n) })).collect())),
        _ => Err(Fault::invalid("expected a proper list")),
    }
}
pub fn tuple(value: &Term) -> Result<&[Term]> {
    match value {
        Term::Tuple(value) => Ok(&value.elements),
        _ => Err(Fault::invalid("expected a protocol request tuple")),
    }
}
pub fn number(value: &Term) -> Result<BigInt> {
    match value {
        Term::FixInteger(value) => Ok(value.value.into()),
        Term::BigInteger(value) => Ok(value.value.clone()),
        _ => Err(Fault::invalid("expected an integer")),
    }
}
pub fn unsigned(value: &Term) -> Result<u64> {
    number(value)?.to_u64().ok_or_else(|| Fault::invalid("expected a nonnegative u64"))
}
pub fn boolean(value: &Term) -> Result<bool> {
    match value {
        Term::Atom(value) if value.name == "true" => Ok(true),
        Term::Atom(value) if value.name == "false" => Ok(false),
        _ => Err(Fault::invalid("expected a Boolean literal")),
    }
}
pub fn field<'a>(value: &'a Term, key: &str) -> Result<&'a Term> {
    match value {
        Term::Map(value) => value.map.get(&binary(key))
            .ok_or_else(|| Fault::invalid(format!("missing data field {key}"))),
        _ => Err(Fault::invalid("expected data map with binary keys")),
    }
}
