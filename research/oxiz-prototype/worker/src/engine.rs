//! A deliberately bounded native fragment. Unsupported input is an error;
//! it must never become a fresh Boolean or an omitted assertion.
use crate::wire::{self, Result};
use eetf::{Map, Term};
use num_traits::ToPrimitive;
use oxiz_core::ast::{TermId, TermKind, TermManager};
use oxiz_core::sort::SortId;
use oxiz_solver::{Solver, SolverConfig, SolverResult};
use std::collections::{BTreeMap, HashMap};
use std::time::{Duration, Instant};

#[derive(Clone)]
struct Definition { params: Vec<(String, SortId)>, result: SortId, body: Term }
#[derive(Clone, Default)]
struct Names {
    constants: BTreeMap<String, TermId>,
    functions: HashMap<String, (Vec<SortId>, SortId)>,
    definitions: HashMap<String, Definition>,
}
pub struct Engine {
    tm: TermManager,
    solver: Solver,
    names: Names,
    scopes: Vec<Names>,
    checks: u64,
}
impl Engine {
    pub fn new() -> Self {
        let mut solver = Solver::with_config(SolverConfig {
            timeout_ms: 1000, parallel: false, num_threads: 1, model: true,
            ..SolverConfig::default()
        });
        solver.set_logic("ALL");
        Self { tm: TermManager::new(), solver, names: Names::default(), scopes: vec![], checks: 0 }
    }
    fn sort(&mut self, form: &Term) -> Result<SortId> {
        match wire::symbol(form)? {
            "Bool" => Ok(self.tm.sorts.bool_sort),
            "Int" => Ok(self.tm.sorts.int_sort),
            "String" => Ok(self.tm.sorts.string_sort()),
            s => Err(format!("unsupported sort: {s}")),
        }
    }
    fn term_sort(&self, term: TermId) -> SortId { self.tm.get(term).expect("owned term").sort }
    fn expect_sort(&self, term: TermId, sort: SortId) -> Result<()> {
        if self.term_sort(term) == sort { Ok(()) } else { Err("sort mismatch".into()) }
    }
    fn arity(args: &[TermId], n: usize) -> Result<()> {
        if args.len() == n { Ok(()) } else { Err(format!("expected {n} operands")) }
    }
    fn expression(&mut self, form: &Term, locals: &HashMap<String, TermId>, depth: usize) -> Result<TermId> {
        if depth > 128 || self.tm.len() > 100_000 { return Err("term capacity exceeded".into()); }
        match form {
            Term::FixInteger(_) | Term::BigInteger(_) => return Ok(self.tm.mk_int(wire::number(form)?)),
            Term::Binary(_) => return Ok(self.tm.mk_string_lit(wire::text(form)?)),
            Term::Atom(a) if a.name == "true" || a.name == "false" => return Ok(self.tm.mk_bool(a.name == "true")),
            Term::Tuple(_) => {
                let name = wire::symbol(form)?;
                return locals.get(name).or_else(|| self.names.constants.get(name)).copied()
                    .ok_or_else(|| format!("undeclared constant: {name}"));
            }
            _ => {}
        }
        let parts = wire::items(form)?;
        let op = wire::symbol(parts.first().ok_or("empty application")?)?;
        if op == "let" {
            if parts.len() != 3 { return Err("let requires bindings and a body".into()); }
            let mut inner = locals.clone();
            for binding in wire::items(&parts[1])? {
                let pair = wire::items(binding)?;
                if pair.len() != 2 { return Err("invalid let binding".into()); }
                // SMT-LIB let bindings are simultaneous, not sequential.
                let value = self.expression(&pair[1], locals, depth + 1)?;
                let name = wire::symbol(&pair[0])?.to_owned();
                if inner.insert(name, value).is_some() { return Err("shadowed let binding unsupported".into()); }
            }
            return self.expression(&parts[2], &inner, depth + 1);
        }
        let mut args = Vec::new();
        for arg in &parts[1..] { args.push(self.expression(arg, locals, depth + 1)?); }
        if let Some(def) = self.names.definitions.get(op).cloned() {
            Self::arity(&args, def.params.len())?;
            let mut inner = HashMap::new();
            for ((name, sort), arg) in def.params.iter().zip(args) {
                self.expect_sort(arg, *sort)?;
                inner.insert(name.clone(), arg);
            }
            let value = self.expression(&def.body, &inner, depth + 1)?;
            self.expect_sort(value, def.result)?;
            return Ok(value);
        }
        if let Some((sorts, result)) = self.names.functions.get(op).cloned() {
            Self::arity(&args, sorts.len())?;
            for (arg, sort) in args.iter().zip(sorts) { self.expect_sort(*arg, sort)?; }
            return Ok(self.tm.mk_apply(op, args, result));
        }
        let bool_sort = self.tm.sorts.bool_sort;
        let int_sort = self.tm.sorts.int_sort;
        let string_sort = self.tm.sorts.string_sort();
        match op {
            "and" | "or" | "not" | "=>" | "xor" => {
                for arg in &args { self.expect_sort(*arg, bool_sort)?; }
                match op {
                    "and" => Ok(self.tm.mk_and(args)), "or" => Ok(self.tm.mk_or(args)),
                    "not" => { Self::arity(&args, 1)?; Ok(self.tm.mk_not(args[0])) },
                    "=>" => { Self::arity(&args, 2)?; Ok(self.tm.mk_implies(args[0], args[1])) },
                    _ => { Self::arity(&args, 2)?; Ok(self.tm.mk_xor(args[0], args[1])) },
                }
            }
            "=" | "distinct" => {
                if args.len() < 2 { return Err("equality requires at least two operands".into()); }
                for arg in &args { self.expect_sort(*arg, self.term_sort(args[0]))?; }
                if op == "distinct" { return Ok(self.tm.mk_distinct(args)); }
                let equalities = args.windows(2).map(|p| self.tm.mk_eq(p[0], p[1])).collect::<Vec<_>>();
                Ok(self.tm.mk_and(equalities))
            }
            "ite" => {
                Self::arity(&args, 3)?;
                self.expect_sort(args[0], bool_sort)?;
                self.expect_sort(args[1], self.term_sort(args[2]))?;
                Ok(self.tm.mk_ite(args[0], args[1], args[2]))
            }
            "+" | "-" | "*" | "div" | "mod" | "<" | "<=" | ">" | ">=" => {
                for arg in &args { self.expect_sort(*arg, int_sort)?; }
                match op {
                    "+" => Ok(self.tm.mk_add(args)), "*" => Ok(self.tm.mk_mul(args)),
                    "-" if args.len() == 1 => Ok(self.tm.mk_neg(args[0])),
                    "-" => { Self::arity(&args, 2)?; Ok(self.tm.mk_sub(args[0], args[1])) },
                    _ => {
                        Self::arity(&args, 2)?;
                        Ok(match op {
                            "div" => self.tm.mk_div(args[0], args[1]), "mod" => self.tm.mk_mod(args[0], args[1]),
                            "<" => self.tm.mk_lt(args[0], args[1]), "<=" => self.tm.mk_le(args[0], args[1]),
                            ">" => self.tm.mk_gt(args[0], args[1]), _ => self.tm.mk_ge(args[0], args[1]),
                        })
                    }
                }
            }
            "str.len" => { Self::arity(&args, 1)?; self.expect_sort(args[0], string_sort)?; Ok(self.tm.mk_str_len(args[0])) },
            "str.++" | "str.contains" | "str.prefixof" | "str.suffixof" => {
                Self::arity(&args, 2)?;
                for arg in &args { self.expect_sort(*arg, string_sort)?; }
                Ok(match op {
                    "str.++" => self.tm.mk_str_concat(args[0], args[1]),
                    "str.contains" => self.tm.mk_str_contains(args[0], args[1]),
                    "str.prefixof" => self.tm.mk_str_prefixof(args[0], args[1]),
                    _ => self.tm.mk_str_suffixof(args[0], args[1]),
                })
            }
            _ => Err(format!("unsupported operator: {op}")),
        }
    }
    fn vacant(&self, name: &str) -> Result<()> {
        if name.starts_with("\\oxiz.") { return Err("reserved solver symbol prefix".into()); }
        if self.names.constants.contains_key(name) || self.names.functions.contains_key(name) || self.names.definitions.contains_key(name) {
            Err(format!("duplicate declaration: {name}"))
        } else { Ok(()) }
    }
    fn command(&mut self, form: &Term) -> Result<()> {
        let parts = wire::items(form)?;
        let op = wire::symbol(parts.first().ok_or("empty command")?)?;
        match op {
            "declare-const" if parts.len() == 3 => {
                let name = wire::symbol(&parts[1])?;
                self.vacant(name)?;
                let sort = self.sort(&parts[2])?;
                let term = self.tm.mk_var(name, sort);
                self.solver.register_declared_const(term, sort);
                self.names.constants.insert(name.to_owned(), term);
            }
            "declare-fun" if parts.len() == 4 => {
                let name = wire::symbol(&parts[1])?;
                self.vacant(name)?;
                let sorts = wire::items(&parts[2])?.iter().map(|s| self.sort(s)).collect::<Result<Vec<_>>>()?;
                let result = self.sort(&parts[3])?;
                if sorts.is_empty() {
                    let term = self.tm.mk_var(name, result);
                    self.solver.register_declared_const(term, result);
                    self.names.constants.insert(name.to_owned(), term);
                } else { self.names.functions.insert(name.to_owned(), (sorts, result)); }
            }
            "define-fun" if parts.len() == 5 => {
                let name = wire::symbol(&parts[1])?;
                self.vacant(name)?;
                let mut params = Vec::new();
                for p in wire::items(&parts[2])? {
                    let pair = wire::items(p)?;
                    if pair.len() != 2 { return Err("invalid parameter".into()); }
                    let param = wire::symbol(&pair[0])?.to_owned();
                    if params.iter().any(|(n, _)| n == &param) { return Err("duplicate parameter".into()); }
                    params.push((param, self.sort(&pair[1])?));
                }
                let def = Definition { params, result: self.sort(&parts[3])?, body: parts[4].clone() };
                // Validate even an unused definition. Fresh local terms are not assertions.
                let locals = def.params.iter().map(|(n,s)| (n.clone(), self.tm.mk_var(&format!("\\oxiz.prototype.{n}"), *s))).collect();
                let body = self.expression(&def.body, &locals, 0)?;
                self.expect_sort(body, def.result)?;
                self.names.definitions.insert(name.to_owned(), def);
            }
            "assert" if parts.len() == 2 => {
                let annotated = wire::items(&parts[1]).ok().filter(|p| p.first().and_then(|t| wire::symbol(t).ok()) == Some("!"));
                if let Some(p) = annotated {
                    if p.len() != 4 || wire::symbol(&p[2])? != ":named" { return Err("unsupported assertion annotation".into()); }
                    let expr = self.expression(&p[1], &HashMap::new(), 0)?;
                    self.expect_sort(expr, self.tm.sorts.bool_sort)?;
                    self.solver.assert_named(expr, wire::symbol(&p[3])?, &mut self.tm);
                } else {
                    let expr = self.expression(&parts[1], &HashMap::new(), 0)?;
                    self.expect_sort(expr, self.tm.sorts.bool_sort)?;
                    self.solver.assert(expr, &mut self.tm);
                }
            }
            "set-logic" if parts.len() == 2 && self.names.constants.is_empty() && self.scopes.is_empty() => {
                let logic = wire::symbol(&parts[1])?;
                if !["ALL", "QF_UF", "QF_LIA", "QF_UFLIA", "QF_S"].contains(&logic) { return Err("unsupported logic".into()); }
                self.solver.set_logic(logic);
            }
            "push" if parts.len() == 2 && wire::number(&parts[1])? == 1.into() => self.push()?,
            "pop" if parts.len() == 2 && wire::number(&parts[1])? == 1.into() => self.pop()?,
            _ => return Err(format!("unsupported command or arity: {op}")),
        }
        Ok(())
    }
    fn push(&mut self) -> Result<()> {
        if self.scopes.len() >= 32 { return Err("scope capacity exceeded".into()); }
        self.scopes.push(self.names.clone()); self.solver.push(); Ok(())
    }
    fn commands(&mut self, forms: &Term) -> Result<()> {
        let forms = wire::items(forms)?;
        if forms.len() > 4096 { return Err("command capacity exceeded".into()); }
        for form in forms { self.command(form)?; }
        Ok(())
    }
    fn pop(&mut self) -> Result<()> {
        self.names = self.scopes.pop().ok_or("scope underflow")?; self.solver.pop(); Ok(())
    }
    fn scalar(&self, id: TermId) -> Result<Term> {
        match &self.tm.get(id).ok_or("missing model term")?.kind {
            TermKind::True => Ok(wire::atom("true")), TermKind::False => Ok(wire::atom("false")),
            TermKind::IntConst(n) => Ok(wire::integer(n.clone())),
            TermKind::StringLit(s) => Ok(wire::binary(s)),
            _ => Err("non-concrete scalar model".into()),
        }
    }
    fn check(&mut self, budget: u64, assumptions: &[Term]) -> Result<Term> {
        if budget == 0 || budget > 10_000 { return Err("budget must be 1..10000ms".into()); }
        let mut terms = Vec::new();
        for form in assumptions {
            let term = self.expression(form, &HashMap::new(), 0)?;
            self.expect_sort(term, self.tm.sorts.bool_sort)?;
            terms.push(term);
        }
        self.solver.set_timeout(Duration::from_millis(budget));
        let started = Instant::now();
        let result = if terms.is_empty() { self.solver.check(&mut self.tm) }
                     else { self.solver.check_with_assumptions(&terms, &mut self.tm) };
        self.checks += 1;
        let model = if result == SolverResult::Sat {
            let mut values = HashMap::new();
            if let Some(model) = self.solver.model().cloned() {
                for (name, term) in &self.names.constants {
                    let value = model.eval(*term, &mut self.tm);
                    values.insert(wire::binary(name), self.scalar(value)?);
                }
            } else { return Err("sat without a model".into()); }
            Map::from(values).into()
        } else { Map::from(HashMap::<Term, Term>::new()).into() };
        let core = self.solver.get_unsat_core().map(|c| c.names.iter().map(|s| wire::binary(s)).collect()).unwrap_or_default();
        Ok(wire::map(vec![
            ("ok", wire::atom("true")), ("backend", wire::binary("oxiz-0.3.4")),
            ("status", wire::atom(match result { SolverResult::Sat => "sat", SolverResult::Unsat => "unsat", SolverResult::Unknown => "unknown" })),
            ("model", model), ("core", wire::list(core)),
            // Low-level API does not expose an exact timeout/incompleteness reason.
            ("why", wire::atom(if result == SolverResult::Unknown { "unspecified" } else { "nil" })),
            ("us", wire::integer(started.elapsed().as_micros())),
            ("checks", wire::integer(self.checks)), ("terms", wire::integer(self.tm.len())),
        ]))
    }
    pub fn request(&mut self, request: &Term) -> Result<Term> {
        let p = wire::fields(request)?;
        let op = wire::text(p.first().ok_or("empty request")?)?;
        match op {
            "hello" if p.len() == 1 => Ok(wire::map(vec![("ok", wire::atom("true")), ("backend", wire::binary("oxiz-0.3.4")), ("pid", wire::integer(std::process::id()))])),
            "reset" if p.len() == 1 => { *self = Self::new(); Ok(wire::ok()) },
            "begin" if p.len() == 2 => {
                *self = Self::new(); self.commands(&p[1])?; Ok(wire::ok())
            }
            "query" if p.len() == 4 => {
                *self = Self::new(); self.commands(&p[1])?;
                self.check(wire::number(&p[2])?.to_u64().ok_or("invalid budget")?, wire::items(&p[3])?)
            }
            "scoped" if p.len() == 4 => {
                self.push()?;
                let result = (|| {
                    self.commands(&p[1])?;
                    self.check(wire::number(&p[2])?.to_u64().ok_or("invalid budget")?, wire::items(&p[3])?)
                })();
                let cleanup = self.pop();
                match result { Ok(reply) => { cleanup?; Ok(reply) }, Err(e) => Err(e) }
            }
            "commands" if p.len() == 2 => {
                self.commands(&p[1])?;
                Ok(wire::ok())
            }
            "push" if p.len() == 1 => { self.push()?; Ok(wire::ok()) },
            "pop" if p.len() == 1 => { self.pop()?; Ok(wire::ok()) },
            "check" if p.len() == 3 => self.check(wire::number(&p[1])?.to_u64().ok_or("invalid budget")?, wire::items(&p[2])?),
            _ => Err(format!("unsupported request or arity: {op}")),
        }
    }
}
