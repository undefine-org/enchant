//! Native OxiZ adapter. Context, rather than the bare Solver, retains its
//! array/model honesty gates. No script parser, model printer or textual core
//! fallback participates in this interface.
use super::{Backend, Check};
use super::dag::{Graph, Node, Sort, ALL_OPS};
use super::wire::{self, Fault, Result};
use eetf::Term;
use num_bigint::BigInt;
use num_rational::{BigRational, Rational64};
use num_traits::{One, ToPrimitive, Zero};
use oxiz_core::ast::{RoundingMode, TermId, TermKind};
use oxiz_core::sort::{DataTypeConstructor, SortId, SortKind};
use oxiz_solver::{Context, SolverResult};
use std::collections::HashMap;
use std::time::Instant;

pub struct Oxiz {
    context: Context,
    terms: HashMap<u64, TermId>,
    sorts: HashMap<Sort, SortId>,
    term_sorts: HashMap<u64, Sort>,
    functions: HashMap<String, (Vec<Sort>, Sort)>,
    enum_names: HashMap<String, (String, String)>,
    depth: usize,
}

impl Oxiz {
    pub fn new() -> Self {
        let mut context = Context::new();
        context.set_logic("ALL");
        Self { context, terms: HashMap::new(), sorts: HashMap::new(),
            term_sorts: HashMap::new(), functions: HashMap::new(), enum_names: HashMap::new(), depth: 0 }
    }
    fn enum_constructor(name: &str, constructor: &str) -> String {
        format!("\\formal.enum.{}.{}.{}", name.len(), name, constructor)
    }
    fn variable_name(bound: bool, name: &str) -> String {
        format!("\\formal.{}.{}", if bound { "bound" } else { "var" }, name)
    }
    fn rounding(data: &Term) -> Result<RoundingMode> {
        match wire::binary_text(data)? {
            "RNE" => Ok(RoundingMode::RNE), "RNA" => Ok(RoundingMode::RNA),
            "RTP" => Ok(RoundingMode::RTP), "RTN" => Ok(RoundingMode::RTN),
            "RTZ" => Ok(RoundingMode::RTZ),
            _ => Err(Fault::invalid("invalid rounding mode")),
        }
    }
    fn contains_rounding(sort: &Sort) -> bool {
        match sort {
            Sort::Rounding => true,
            Sort::Array(k, v) => Self::contains_rounding(k) || Self::contains_rounding(v),
            Sort::Seq(e) => Self::contains_rounding(e),
            _ => false,
        }
    }
    fn sort(&mut self, sort: &Sort) -> Result<SortId> {
        if let Some(id) = self.sorts.get(sort) { return Ok(*id); }
        let id = match sort {
            Sort::Bool => self.context.terms.sorts.bool_sort,
            Sort::Int => self.context.terms.sorts.int_sort,
            Sort::Real => self.context.terms.sorts.real_sort,
            Sort::String => self.context.terms.sorts.string_sort(),
            Sort::Bv(w) => self.context.terms.sorts.bitvec(*w),
            Sort::Fp(e, s) => self.context.terms.sorts.float_sort(*e, *s),
            Sort::Rounding => self.context.terms.sorts.intern(SortKind::RoundingMode),
            Sort::Seq(_) => return Err(Fault::unsupported("OxiZ has no native generic sequence sort")),
            Sort::Array(k, v) => {
                if Self::contains_rounding(k) || Self::contains_rounding(v) {
                    return Err(Fault::unsupported("OxiZ native rounding-mode closure is only exposed for scalar constants"));
                }
                let key = self.sort(k)?; let value = self.sort(v)?;
                self.context.terms.sorts.array(key, value)
            }
            Sort::Uninterpreted(name) => {
                let symbol = self.context.terms.sorts.intern_str(&format!("formal.sort.{name}"));
                self.context.terms.sorts.intern(SortKind::Uninterpreted(symbol))
            }
            Sort::Enum(name, constructors) => {
                let internal = format!("formal.enum.{name}");
                let mut declarations = Vec::new();
                for constructor in constructors {
                    let native = Self::enum_constructor(name, constructor);
                    let symbol = self.context.terms.intern_str(&native);
                    declarations.push(DataTypeConstructor { name: symbol, selectors: Default::default() });
                    self.enum_names.insert(native, (name.clone(), constructor.clone()));
                }
                self.context.terms.sorts.declare_datatype(&internal, declarations);
                self.context.terms.sorts.mk_datatype_sort(&internal)
            }
        };
        self.sorts.insert(sort.clone(), id);
        Ok(id)
    }
    fn term(&self, id: u64) -> Result<TermId> {
        self.terms.get(&id).copied().ok_or_else(|| Fault::invalid(format!("native term {id} is missing")))
    }
    fn real_literal(&mut self, data: &Term) -> Result<TermId> {
        let pair = wire::items(data)?;
        let value = BigRational::new(wire::number(&pair[0])?, wire::number(&pair[1])?);
        let numerator = value.numer().to_i64().ok_or_else(|| Fault::unsupported("OxiZ native RealConst numerator exceeds i64"))?;
        let denominator = value.denom().to_i64().ok_or_else(|| Fault::unsupported("OxiZ native RealConst denominator exceeds i64"))?;
        Ok(self.context.terms.mk_real(Rational64::new(numerator, denominator)))
    }
    fn observe(&mut self, id: u64) -> Term {
        let Some(term) = self.terms.get(&id).copied() else {
            return wire::tagged("unavailable", [wire::binary("missing native term")]);
        };
        let Some(value) = self.context.eval_in_model(term) else {
            return wire::tagged("unavailable", [wire::binary("OxiZ did not publish a model value")]);
        };
        self.value(value, self.term_sorts.get(&id), 0)
    }
    fn value(&self, id: TermId, expected: Option<&Sort>, depth: usize) -> Term {
        if depth > 128 { return wire::tagged("opaque", [wire::binary("model nesting exceeds 128")]); }
        let Some(value) = self.context.terms.get(id) else {
            return wire::tagged("unavailable", [wire::binary("missing OxiZ model term")]);
        };
        match &value.kind {
            TermKind::True => wire::tagged("bool", [wire::atom("true")]),
            TermKind::False => wire::tagged("bool", [wire::atom("false")]),
            TermKind::IntConst(number) => {
                if expected == Some(&Sort::Real) {
                    wire::tagged("real", [wire::integer(number.clone()), wire::integer(1)])
                } else { wire::tagged("int", [wire::integer(number.clone())]) }
            }
            TermKind::RealConst(number) => {
                if expected == Some(&Sort::Int) && *number.denom() == 1 {
                    wire::tagged("int", [wire::integer(*number.numer())])
                } else { wire::tagged("real", [wire::integer(*number.numer()), wire::integer(*number.denom())]) }
            }
            TermKind::StringLit(text) => wire::tagged("text", [wire::binary(text)]),
            TermKind::BitVecConst { value, width } => wire::tagged("bv", [wire::integer(*width), wire::integer(value.clone())]),
            TermKind::DtConstructor { constructor, args } => {
                let name = self.context.terms.resolve_str(*constructor);
                if let Some((sort, constructor)) = self.enum_names.get(name) {
                    wire::tagged("enum", [wire::binary(sort), wire::binary(constructor)])
                } else {
                    wire::tagged("constructor", [wire::binary(name),
                        wire::list(args.iter().map(|arg| self.value(*arg, None, depth + 1)))])
                }
            }
            TermKind::FpLit { sign, exp, sig, eb, sb } => {
                let bits = (if *sign { BigInt::one() << (*eb + *sb - 1) } else { BigInt::zero() })
                    | (exp << (*sb - 1)) | sig;
                let max_exp = (BigInt::one() << *eb) - 1;
                if exp == &max_exp && !sig.is_zero() {
                    wire::tagged("opaque", [wire::binary("SMT FP NaN has no stable IEEE payload identity")])
                } else { wire::tagged("fp", [wire::integer(*eb), wire::integer(*sb), wire::integer(bits)]) }
            }
            TermKind::FpPlusZero { eb, sb } => wire::tagged("fp", [wire::integer(*eb), wire::integer(*sb), wire::integer(0)]),
            TermKind::FpMinusZero { eb, sb } => wire::tagged("fp", [wire::integer(*eb), wire::integer(*sb), wire::integer(BigInt::one() << (*eb + *sb - 1))]),
            TermKind::FpPlusInfinity { eb, sb } | TermKind::FpMinusInfinity { eb, sb } => {
                let sign = matches!(value.kind, TermKind::FpMinusInfinity { .. });
                let bits = (((BigInt::one() << *eb) - 1) << (*sb - 1))
                    | if sign { BigInt::one() << (*eb + *sb - 1) } else { BigInt::zero() };
                wire::tagged("fp", [wire::integer(*eb), wire::integer(*sb), wire::integer(bits)])
            }
            TermKind::FpNaN { .. } => wire::tagged("opaque", [wire::binary("SMT FP NaN has no stable IEEE payload identity")]),
            _ => wire::tagged("opaque", [wire::binary("OxiZ observation is not a materialized scalar/constructor")]),
        }
    }
}

impl Backend for Oxiz {
    fn name(&self) -> &'static str { "oxiz" }
    fn version(&self) -> String { "0.3.4".to_owned() }
    fn capabilities(&self) -> Term {
        let excluded = ["to-real", "to-int", "is-int", "seq-empty", "seq-unit", "seq-concat", "seq-len", "seq-nth", "seq-extract", "fp-to-ieee-bv"];
        wire::map([
            ("operations", wire::list(ALL_OPS.iter().filter(|op| !excluded.contains(op)).map(|op| wire::binary(op)))),
            ("sorts", wire::list(["bool","int","real","string","bv","fp","rounding","array","uninterpreted","enum"].into_iter().map(wire::binary))),
            ("limits", wire::binary_map([
                ("max-bv-width", wire::integer(4096)), ("max-fp-bits", wire::integer(128)),
                ("real-literal-bits", wire::integer(64)), ("symbolic-rounding", wire::atom("false")),
                ("native-cores", wire::atom("false")), ("max-text-codepoint", wire::integer(0x2ffff)),
                ("fp-literal-normalization", wire::binary("all IEEE NaN encodings denote one SMT NaN; payloads remain opaque")),
                ("model", wire::binary("observed native scalars and nullary constructors; opaque otherwise")),
            ])),
        ])
    }
    fn reset(&mut self) -> Result<()> { *self = Self::new(); Ok(()) }
    fn import(&mut self, node: &Node, graph: &Graph) -> Result<()> {
        let sort = self.sort(&node.sort)?;
        let args = node.args.iter().map(|id| self.term(*id)).collect::<Result<Vec<_>>>()?;
        let term = match node.op.as_str() {
            "var" => self.context.declare_const(&Self::variable_name(false, wire::binary_text(&node.data)?), sort),
            "bound" => self.context.terms.mk_var(&Self::variable_name(true, wire::binary_text(&node.data)?), sort),
            "bool" => self.context.terms.mk_bool(wire::boolean(&node.data)?),
            "int" => self.context.terms.mk_int(wire::number(&node.data)?),
            "real" => self.real_literal(&node.data)?,
            "text" => self.context.terms.mk_string_lit(wire::binary_text(&node.data)?),
            "bv" => {
                let Sort::Bv(width) = node.sort else { unreachable!() };
                let modulus = BigInt::one() << width;
                let value = wire::number(&node.data)?;
                self.context.terms.mk_bitvec(((value % &modulus) + &modulus) % &modulus, width)
            }
            "rounding" => self.context.terms.mk_rounding_mode(Self::rounding(&node.data)?),
            "enum" => {
                let Sort::Enum(name, _) = &node.sort else { unreachable!() };
                self.context.terms.mk_dt_constructor(&Self::enum_constructor(name, wire::binary_text(&node.data)?), [], sort)
            }
            "not" => self.context.terms.mk_not(args[0]),
            "and" => self.context.terms.mk_and(args), "or" => self.context.terms.mk_or(args),
            "implies" => self.context.terms.mk_implies(args[0], args[1]),
            "xor" => self.context.terms.mk_xor(args[0], args[1]),
            "eq" => {
                let terms = args.windows(2).map(|p| self.context.terms.mk_eq(p[0],p[1])).collect::<Vec<_>>();
                self.context.terms.mk_and(terms)
            }
            "distinct" => self.context.terms.mk_distinct(args),
            "ite" => self.context.terms.mk_ite(args[0], args[1], args[2]),
            "add" | "mul" if args.is_empty() => {
                let value = if node.op == "add" { 0 } else { 1 };
                if node.sort == Sort::Real { self.context.terms.mk_real(Rational64::from_integer(value)) }
                else { self.context.terms.mk_int(value) }
            }
            "add" => self.context.terms.mk_add(args), "mul" => self.context.terms.mk_mul(args),
            "sub" => self.context.terms.mk_sub(args[0],args[1]), "neg" => self.context.terms.mk_neg(args[0]),
            "div" => self.context.terms.mk_div(args[0],args[1]), "mod" => self.context.terms.mk_mod(args[0],args[1]),
            "lt" => self.context.terms.mk_lt(args[0],args[1]), "le" => self.context.terms.mk_le(args[0],args[1]),
            "gt" => self.context.terms.mk_gt(args[0],args[1]), "ge" => self.context.terms.mk_ge(args[0],args[1]),
            "array-const" => self.context.terms.mk_apply(oxiz_core::smtlib::CONST_ARRAY_FUNC, [args[0]], sort),
            "select" => self.context.terms.mk_select(args[0],args[1]),
            "store" => self.context.terms.mk_store(args[0],args[1],args[2]),
            "str-concat" => {
                let mut result = self.context.terms.mk_string_lit("");
                for arg in args { result = self.context.terms.mk_str_concat(result,arg); }
                result
            }
            "str-len" => self.context.terms.mk_str_len(args[0]),
            "str-contains" => self.context.terms.mk_str_contains(args[0],args[1]),
            "str-prefix" => self.context.terms.mk_str_prefixof(args[0],args[1]),
            "str-suffix" => self.context.terms.mk_str_suffixof(args[0],args[1]),
            "str-at" => self.context.terms.mk_str_at(args[0],args[1]),
            "str-substr" => self.context.terms.mk_str_substr(args[0],args[1],args[2]),
            "str-index" => self.context.terms.mk_str_indexof(args[0],args[1],args[2]),
            "str-replace" => self.context.terms.mk_str_replace(args[0],args[1],args[2]),
            "bv-not" => self.context.terms.mk_bv_not(args[0]), "bv-neg" => self.context.terms.mk_bv_neg(args[0]),
            "bv-add" => self.context.terms.mk_bv_add(args[0],args[1]), "bv-sub" => self.context.terms.mk_bv_sub(args[0],args[1]),
            "bv-mul" => self.context.terms.mk_bv_mul(args[0],args[1]), "bv-and" => self.context.terms.mk_bv_and(args[0],args[1]),
            "bv-or" => self.context.terms.mk_bv_or(args[0],args[1]), "bv-xor" => self.context.terms.mk_bv_xor(args[0],args[1]),
            "bv-shl" => self.context.terms.mk_bv_shl(args[0],args[1]), "bv-lshr" => self.context.terms.mk_bv_lshr(args[0],args[1]),
            "bv-ashr" => self.context.terms.mk_bv_ashr(args[0],args[1]),
            "bv-ult" => self.context.terms.mk_bv_ult(args[0],args[1]), "bv-ule" => self.context.terms.mk_bv_ule(args[0],args[1]),
            "bv-slt" => self.context.terms.mk_bv_slt(args[0],args[1]), "bv-sle" => self.context.terms.mk_bv_sle(args[0],args[1]),
            "bv-concat" => self.context.terms.try_mk_bv_concat(args[0],args[1]).map_err(|e| Fault::invalid(e.to_string()))?,
            "bv-extract" => {
                let indices = wire::items(&node.data)?;
                self.context.terms.mk_bv_extract(wire::unsigned(&indices[0])? as u32, wire::unsigned(&indices[1])? as u32,args[0])
            }
            "bv-zero-extend" | "bv-sign-extend" => {
                let extra = wire::unsigned(&node.data)? as u32;
                if extra == 0 { args[0] } else {
                    let zero = self.context.terms.mk_bitvec(0,extra);
                    let high = if node.op == "bv-sign-extend" {
                        let Sort::Bv(width) = graph[&node.args[0]].sort else { unreachable!() };
                        let bit = self.context.terms.mk_bv_extract(width-1,width-1,args[0]);
                        let one = self.context.terms.mk_bitvec(1,1);
                        let negative = self.context.terms.mk_eq(bit,one);
                        let ones = self.context.terms.mk_bitvec((BigInt::one() << extra)-1,extra);
                        self.context.terms.mk_ite(negative,ones,zero)
                    } else { zero };
                    self.context.terms.try_mk_bv_concat(high,args[0]).map_err(|e| Fault::invalid(e.to_string()))?
                }
            }
            "uf" => {
                let name = wire::binary_text(wire::field(&node.data,"name")?)?;
                let domain = wire::items(wire::field(&node.data,"domain")?)?.iter().map(Sort::parse).collect::<Result<Vec<_>>>()?;
                if domain.iter().any(Self::contains_rounding) || Self::contains_rounding(&node.sort) {
                    return Err(Fault::unsupported("OxiZ native UF signatures containing RoundingMode need additional closure machinery"));
                }
                if let Some(signature) = self.functions.get(name) {
                    if signature != &(domain.clone(),node.sort.clone()) { return Err(Fault::invalid("UF signature was changed")); }
                } else {
                    let domains = domain.iter().map(|s| self.sort(s)).collect::<Result<Vec<_>>>()?;
                    self.context.declare_fun(&format!("\\formal.uf.{name}"),domains,sort);
                    self.functions.insert(name.to_owned(),(domain,node.sort.clone()));
                }
                self.context.terms.mk_apply(&format!("\\formal.uf.{name}"),args,sort)
            }
            "forall" | "exists" => {
                let binders = node.binders()?;
                if binders.iter().any(|(_,s)| Self::contains_rounding(s)) {
                    return Err(Fault::unsupported("OxiZ native RoundingMode quantification requires parser-side domain relativization"));
                }
                let mut native = Vec::new();
                for (name, sort) in binders { native.push((Self::variable_name(true,&name),self.sort(&sort)?)); }
                let variables = native.iter().map(|(name,sort)| (name.as_str(),*sort));
                if node.op == "forall" { self.context.terms.mk_forall(variables,args[0]) }
                else { self.context.terms.mk_exists(variables,args[0]) }
            }
            "fp-bits" => {
                let Sort::Fp(eb,sb) = node.sort else { unreachable!() };
                let bits = wire::number(&node.data)?;
                if bits < BigInt::zero() || bits >= (BigInt::one() << (eb+sb)) { return Err(Fault::invalid("IEEE bit pattern exceeds format")); }
                let sign = ((&bits >> (eb+sb-1)) & BigInt::one()) == BigInt::one();
                let exp = (&bits >> (sb-1)) & ((BigInt::one()<<eb)-1);
                let sig = bits & ((BigInt::one()<<(sb-1))-1);
                // The SMT FP sort has exactly one NaN. OxiZ's raw FpLit
                // constructor preserves sign/payload and bare FP equalities
                // can otherwise remain in its EUF route. Normalize this
                // semantic value before interning; IEEE payload identity is
                // a BV question and is never an FP model observation.
                if exp == (BigInt::one() << eb)-1 && !sig.is_zero() {
                    self.context.terms.mk_fp_nan(eb,sb)
                } else { self.context.terms.mk_fp_lit(sign,exp,sig,eb,sb) }
            }
            "fp-neg" => self.context.terms.mk_fp_neg(args[0]),
            "fp-eq" => self.context.terms.mk_fp_eq(args[0],args[1]),
            "fp-lt" => self.context.terms.mk_fp_lt(args[0],args[1]),
            "fp-le" => self.context.terms.mk_fp_leq(args[0],args[1]),
            "fp-is-nan" => self.context.terms.mk_fp_is_nan(args[0]),
            "fp-is-inf" => self.context.terms.mk_fp_is_infinite(args[0]),
            "fp-add" | "fp-sub" | "fp-mul" | "fp-div" => {
                let rounding = &graph[&node.args[0]];
                if rounding.op != "rounding" { return Err(Fault::unsupported("OxiZ native FP arithmetic currently requires a literal rounding mode")); }
                let mode = Self::rounding(&rounding.data)?;
                match node.op.as_str() {
                    "fp-add" => self.context.terms.mk_fp_add(mode,args[1],args[2]),
                    "fp-sub" => self.context.terms.mk_fp_sub(mode,args[1],args[2]),
                    "fp-mul" => self.context.terms.mk_fp_mul(mode,args[1],args[2]),
                    _ => self.context.terms.mk_fp_div(mode,args[1],args[2]),
                }
            }
            op => return Err(Fault::unsupported(format!("OxiZ native operation {op} is not exposed by this adapter"))),
        };
        if self.context.terms.get(term).is_none_or(|term| term.sort != sort) {
            return Err(Fault::backend(format!("OxiZ native builder returned a different sort for {}",node.op)));
        }
        self.terms.insert(node.id,term);
        self.term_sorts.insert(node.id,node.sort.clone());
        Ok(())
    }
    fn assert(&mut self, id: u64, label: &str) -> Result<()> {
        let term = self.term(id)?;
        self.context.assert_named(term,label);
        Ok(())
    }
    fn push(&mut self) -> Result<()> {
        if self.depth >= 32 { return Err(Fault::invalid("scope depth exceeds 32")); }
        self.context.push(); self.depth += 1; Ok(())
    }
    fn pop(&mut self) -> Result<()> {
        if self.depth == 0 { return Err(Fault::invalid("scope underflow")); }
        self.context.pop(); self.depth -= 1; Ok(())
    }
    fn check(&mut self, assumptions: &[u64], observations: &[(String,u64)], budget: u64) -> Result<Check> {
        self.context.set_timeout_ms(budget);
        if !assumptions.is_empty() {
            self.push()?;
            for assumption in assumptions { let term = self.term(*assumption)?; self.context.assert(term); }
        }
        let started = Instant::now();
        let result = self.context.check_sat();
        let solve_us = started.elapsed().as_micros();
        let values = if result == SolverResult::Sat {
            observations.iter().map(|(label,id)| (label.clone(),self.observe(*id))).collect()
        } else { Vec::new() };
        if !assumptions.is_empty() { self.pop()?; }
        Ok(Check { status: match result { SolverResult::Sat => "sat", SolverResult::Unsat => "unsat", SolverResult::Unknown => "unknown" },
            observations: values, core: vec![], core_kind: "unsupported", reason_kind: "unspecified",
            reason: if result == SolverResult::Unknown { "OxiZ native API did not expose the exact unknown reason".to_owned() } else { String::new() },
            solve_us })
    }
}
