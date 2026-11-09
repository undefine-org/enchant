use super::wire::{self, Fault, Result};
use eetf::Term;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum Sort {
    Bool, Int, Real, String, Bv(u32), Fp(u32, u32), Rounding,
    Array(Box<Sort>, Box<Sort>), Seq(Box<Sort>),
    Uninterpreted(String), Enum(String, Vec<String>),
}

impl Sort {
    pub fn parse(value: &Term) -> Result<Self> { Self::parse_at(value, 0) }
    fn parse_at(value: &Term, depth: usize) -> Result<Self> {
        if depth > 32 { return Err(Fault::invalid("sort nesting exceeds 32")); }
        let values = wire::items(value)?;
        let first = values.first().ok_or_else(|| Fault::invalid("empty sort"))?;
        let tag = wire::binary_text(first)?;
        let sort = match (tag, values.len()) {
            ("bool", 1) => Self::Bool, ("int", 1) => Self::Int,
            ("real", 1) => Self::Real, ("string", 1) => Self::String,
            ("rounding", 1) => Self::Rounding,
            ("bv", 2) => {
                let width = wire::unsigned(&values[1])?;
                if width == 0 { return Err(Fault::invalid("bit-vector width must be positive")); }
                if width > 4096 { return Err(Fault::unsupported("bit-vector width exceeds 4096")); }
                Self::Bv(width as u32)
            }
            ("fp", 3) => {
                let eb = wire::unsigned(&values[1])?;
                let sb = wire::unsigned(&values[2])?;
                if eb < 2 || sb < 2 { return Err(Fault::invalid("FP widths must both be at least 2")); }
                if eb > 64 || sb > 128 || eb + sb > 128 {
                    return Err(Fault::unsupported("FP format exceeds adapter's 128-bit bound"));
                }
                Self::Fp(eb as u32, sb as u32)
            }
            ("array", 3) => Self::Array(
                Box::new(Self::parse_at(&values[1], depth + 1)?),
                Box::new(Self::parse_at(&values[2], depth + 1)?)),
            ("seq", 2) => Self::Seq(Box::new(Self::parse_at(&values[1], depth + 1)?)),
            ("uninterpreted", 2) => Self::Uninterpreted(wire::binary_text(&values[1])?.to_owned()),
            ("enum", 3) => {
                let name = wire::binary_text(&values[1])?.to_owned();
                let variants = wire::items(&values[2])?.iter()
                    .map(|v| wire::binary_text(v).map(str::to_owned)).collect::<Result<Vec<_>>>()?;
                if variants.is_empty() { return Err(Fault::invalid("an enum must have a constructor")); }
                if variants.len() > 1024 { return Err(Fault::unsupported("enum has more than 1024 constructors")); }
                if variants.iter().collect::<BTreeSet<_>>().len() != variants.len() {
                    return Err(Fault::invalid("duplicate enum constructor"));
                }
                Self::Enum(name, variants)
            }
            _ => return Err(Fault::unsupported(format!("unsupported sort or sort arity: {tag}"))),
        };
        Ok(sort)
    }
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Bool => "bool", Self::Int => "int", Self::Real => "real",
            Self::String => "string", Self::Bv(_) => "bv", Self::Fp(_, _) => "fp",
            Self::Rounding => "rounding", Self::Array(_, _) => "array",
            Self::Seq(_) => "seq", Self::Uninterpreted(_) => "uninterpreted", Self::Enum(_, _) => "enum",
        }
    }
    pub fn wire(&self) -> Term {
        let mut values = vec![wire::binary(self.kind())];
        match self {
            Self::Bv(w) => values.push(wire::integer(*w)),
            Self::Fp(e, s) => { values.push(wire::integer(*e)); values.push(wire::integer(*s)); }
            Self::Array(k, v) => { values.push(k.wire()); values.push(v.wire()); }
            Self::Seq(e) => values.push(e.wire()),
            Self::Uninterpreted(name) => values.push(wire::binary(name)),
            Self::Enum(name, ctors) => {
                values.push(wire::binary(name));
                values.push(wire::list(ctors.iter().map(|v| wire::binary(v))));
            }
            _ => {}
        }
        wire::list(values)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Node {
    pub id: u64, pub op: String, pub sort: Sort, pub args: Vec<u64>, pub data: Term,
}
pub type Graph = BTreeMap<u64, Node>;

impl Node {
    pub fn parse(value: &Term) -> Result<Self> {
        let values = wire::items(value)?;
        if values.len() != 5 { return Err(Fault::invalid("a DAG node has five fields")); }
        let args = wire::items(&values[3])?.iter().map(wire::unsigned).collect::<Result<Vec<_>>>()?;
        Ok(Self { id: wire::unsigned(&values[0])?, op: wire::binary_text(&values[1])?.to_owned(),
            sort: Sort::parse(&values[2])?, args, data: values[4].clone() })
    }
    pub fn binders(&self) -> Result<Vec<(String, Sort)>> {
        let mut seen = BTreeSet::new();
        wire::items(&self.data)?.iter().map(|value| {
            let fields = wire::items(value)?;
            if fields.len() != 2 { return Err(Fault::invalid("binder needs name and sort")); }
            let name = wire::binary_text(&fields[0])?.to_owned();
            if !seen.insert(name.clone()) { return Err(Fault::invalid("duplicate binder name")); }
            Ok((name, Sort::parse(&fields[1])?))
        }).collect()
    }
    pub fn validate(&self, graph: &Graph) -> Result<()> {
        let args = self.args.iter().map(|id| graph.get(id)
            .map(|node| node.sort.clone()).ok_or_else(|| Fault::invalid(format!("DAG argument {id} is not imported"))))
            .collect::<Result<Vec<_>>>()?;
        let same = |sort: &Sort| args.iter().all(|s| s == sort);
        let exactly = |n| args.len() == n;
        let result = match self.op.as_str() {
            "var" | "bound" => { wire::binary_text(&self.data)?; exactly(0) }
            "bool" => { wire::boolean(&self.data)?; exactly(0) && self.sort == Sort::Bool }
            "int" => { wire::number(&self.data)?; exactly(0) && self.sort == Sort::Int }
            "real" => {
                let pair = wire::items(&self.data)?;
                if pair.len() != 2 { return Err(Fault::invalid("real literal needs numerator and denominator")); }
                wire::number(&pair[0])?;
                if wire::number(&pair[1])? == 0.into() { return Err(Fault::invalid("zero rational denominator")); }
                exactly(0) && self.sort == Sort::Real
            }
            "text" => {
                let text = wire::binary_text(&self.data)?;
                if text.chars().any(|c| u32::from(c) > 0x2ffff) {
                    return Err(Fault::unsupported("SMT Unicode string alphabet ends at U+2FFFF"));
                }
                exactly(0) && self.sort == Sort::String
            }
            "bv" => { wire::number(&self.data)?; exactly(0) && matches!(self.sort, Sort::Bv(_)) }
            "fp-bits" => { wire::unsigned(&self.data).or_else(|_| {
                if wire::number(&self.data)? < 0.into() { Err(Fault::invalid("negative IEEE bits")) } else { Ok(0) }
            })?; exactly(0) && matches!(self.sort, Sort::Fp(_, _)) }
            "rounding" => {
                let mode = wire::binary_text(&self.data)?;
                if !["RNE", "RNA", "RTP", "RTN", "RTZ"].contains(&mode) { return Err(Fault::invalid("invalid rounding mode")); }
                exactly(0) && self.sort == Sort::Rounding
            }
            "enum" => {
                let constructor = wire::binary_text(&self.data)?;
                matches!(&self.sort, Sort::Enum(_, variants) if variants.iter().any(|v| v == constructor)) && exactly(0)
            }
            "not" => exactly(1) && same(&Sort::Bool) && self.sort == Sort::Bool,
            "and" | "or" => same(&Sort::Bool) && self.sort == Sort::Bool,
            "implies" | "xor" => exactly(2) && same(&Sort::Bool) && self.sort == Sort::Bool,
            "eq" | "distinct" => args.len() >= 2 && same(&args[0]) && self.sort == Sort::Bool,
            "ite" => exactly(3) && args[0] == Sort::Bool && args[1] == args[2] && self.sort == args[1],
            "add" | "mul" => matches!(self.sort, Sort::Int | Sort::Real) && same(&self.sort),
            "sub" => exactly(2) && matches!(self.sort, Sort::Int | Sort::Real) && same(&self.sort),
            "neg" => exactly(1) && matches!(self.sort, Sort::Int | Sort::Real) && same(&self.sort),
            "div" | "mod" => exactly(2) && same(&Sort::Int) && self.sort == Sort::Int,
            "lt" | "le" | "gt" | "ge" => exactly(2) && args[0] == args[1] && matches!(args[0], Sort::Int | Sort::Real) && self.sort == Sort::Bool,
            "to-real" => exactly(1) && args[0] == Sort::Int && self.sort == Sort::Real,
            "to-int" => exactly(1) && args[0] == Sort::Real && self.sort == Sort::Int,
            "is-int" => exactly(1) && args[0] == Sort::Real && self.sort == Sort::Bool,
            "array-const" => matches!(&self.sort, Sort::Array(_, v) if exactly(1) && **v == args[0]),
            "select" => exactly(2) && matches!(&args[0], Sort::Array(k,v) if **k == args[1] && **v == self.sort),
            "store" => exactly(3) && matches!(&args[0], Sort::Array(k,v) if **k == args[1] && **v == args[2] && self.sort == args[0]),
            "str-concat" => same(&Sort::String) && self.sort == Sort::String,
            "str-len" => exactly(1) && same(&Sort::String) && self.sort == Sort::Int,
            "str-contains" | "str-prefix" | "str-suffix" => exactly(2) && same(&Sort::String) && self.sort == Sort::Bool,
            "str-at" => exactly(2) && args[0] == Sort::String && args[1] == Sort::Int && self.sort == Sort::String,
            "str-substr" => exactly(3) && args[0] == Sort::String && args[1] == Sort::Int && args[2] == Sort::Int && self.sort == Sort::String,
            "str-index" => exactly(3) && args[0] == Sort::String && args[1] == Sort::String && args[2] == Sort::Int && self.sort == Sort::Int,
            "str-replace" => exactly(3) && same(&Sort::String) && self.sort == Sort::String,
            "bv-not" | "bv-neg" => exactly(1) && matches!(self.sort, Sort::Bv(_)) && same(&self.sort),
            "bv-add" | "bv-sub" | "bv-mul" | "bv-and" | "bv-or" | "bv-xor" | "bv-shl" | "bv-lshr" | "bv-ashr" => exactly(2) && matches!(self.sort, Sort::Bv(_)) && same(&self.sort),
            "bv-ult" | "bv-ule" | "bv-slt" | "bv-sle" => exactly(2) && args[0] == args[1] && matches!(args[0], Sort::Bv(_)) && self.sort == Sort::Bool,
            "bv-concat" => exactly(2) && matches!((&args[0], &args[1], &self.sort), (Sort::Bv(a),Sort::Bv(b),Sort::Bv(c)) if a.checked_add(*b) == Some(*c)),
            "bv-extract" => {
                let indices = wire::items(&self.data)?;
                if indices.len() != 2 { return Err(Fault::invalid("extract requires high and low")); }
                let high = wire::unsigned(&indices[0])?; let low = wire::unsigned(&indices[1])?;
                exactly(1) && matches!((&args[0], &self.sort), (Sort::Bv(w),Sort::Bv(out)) if low <= high && high < u64::from(*w) && high-low+1 == u64::from(*out))
            }
            "bv-zero-extend" | "bv-sign-extend" => {
                let extension = wire::unsigned(&self.data)?;
                exactly(1) && matches!((&args[0], &self.sort), (Sort::Bv(w),Sort::Bv(out)) if u64::from(*w).checked_add(extension) == Some(u64::from(*out)))
            }
            "seq-empty" => exactly(0) && matches!(self.sort, Sort::Seq(_)),
            "seq-unit" => exactly(1) && matches!(&self.sort, Sort::Seq(e) if **e == args[0]),
            "seq-concat" => matches!(self.sort, Sort::Seq(_)) && same(&self.sort),
            "seq-len" => exactly(1) && matches!(args[0], Sort::Seq(_)) && self.sort == Sort::Int,
            "seq-nth" => exactly(2) && args[1] == Sort::Int && matches!(&args[0], Sort::Seq(e) if **e == self.sort),
            "seq-extract" => exactly(3) && matches!(self.sort, Sort::Seq(_)) && args[0] == self.sort && args[1] == Sort::Int && args[2] == Sort::Int,
            "uf" => {
                wire::binary_text(wire::field(&self.data, "name")?)?;
                let domain = wire::items(wire::field(&self.data, "domain")?)?.iter().map(Sort::parse).collect::<Result<Vec<_>>>()?;
                domain == args && Sort::parse(wire::field(&self.data, "range")?)? == self.sort
            }
            "forall" | "exists" => { self.binders()?; exactly(1) && args[0] == Sort::Bool && self.sort == Sort::Bool }
            "fp-neg" => exactly(1) && matches!(self.sort, Sort::Fp(_, _)) && same(&self.sort),
            "fp-add" | "fp-sub" | "fp-mul" | "fp-div" => exactly(3) && args[0] == Sort::Rounding && args[1] == self.sort && args[2] == self.sort && matches!(self.sort, Sort::Fp(_, _)),
            "fp-eq" | "fp-lt" | "fp-le" => exactly(2) && args[0] == args[1] && matches!(args[0], Sort::Fp(_, _)) && self.sort == Sort::Bool,
            "fp-is-nan" | "fp-is-inf" => exactly(1) && matches!(args[0], Sort::Fp(_, _)) && self.sort == Sort::Bool,
            "fp-to-ieee-bv" => exactly(1) && matches!((&args[0],&self.sort),(Sort::Fp(e,s),Sort::Bv(w)) if e+s == *w),
            other => return Err(Fault::unsupported(format!("operation {other} is outside protocol v1"))),
        };
        if result { Ok(()) } else { Err(Fault::invalid(format!("sort or arity mismatch for {}", self.op))) }
    }
}

pub const ALL_OPS: &[&str] = &[
    "var","bound","bool","int","real","text","bv","fp-bits","rounding","enum",
    "not","and","or","implies","xor","eq","distinct","ite","add","sub","neg","mul","div","mod","lt","le","gt","ge","to-real","to-int","is-int",
    "array-const","select","store","str-concat","str-len","str-contains","str-prefix","str-suffix","str-at","str-substr","str-index","str-replace",
    "bv-add","bv-sub","bv-mul","bv-and","bv-or","bv-xor","bv-not","bv-neg","bv-shl","bv-lshr","bv-ashr","bv-ult","bv-ule","bv-slt","bv-sle","bv-concat","bv-extract","bv-zero-extend","bv-sign-extend",
    "seq-empty","seq-unit","seq-concat","seq-len","seq-nth","seq-extract","uf","forall","exists",
    "fp-add","fp-sub","fp-mul","fp-div","fp-neg","fp-eq","fp-lt","fp-le","fp-is-nan","fp-is-inf","fp-to-ieee-bv",
];
