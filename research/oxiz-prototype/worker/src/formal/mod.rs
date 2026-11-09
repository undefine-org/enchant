pub mod dag;
pub mod wire;
mod oxiz;
mod z3;

use dag::{Graph, Node, Sort};
use eetf::Term;
use std::collections::{BTreeMap, BTreeSet};
use wire::{Fault, Result};

pub struct Check {
    pub status: &'static str,
    pub observations: Vec<(String, Term)>,
    pub core: Vec<String>,
    pub core_kind: &'static str,
    pub reason_kind: &'static str,
    pub reason: String,
    pub solve_us: u128,
}

trait Backend {
    fn name(&self) -> &'static str;
    fn version(&self) -> String;
    fn capabilities(&self) -> Term;
    fn reset(&mut self) -> Result<()>;
    fn import(&mut self, node: &Node, graph: &Graph) -> Result<()>;
    fn assert(&mut self, id: u64, label: &str) -> Result<()>;
    fn push(&mut self) -> Result<()>;
    fn pop(&mut self) -> Result<()>;
    fn check(&mut self, assumptions: &[u64], observations: &[(String, u64)], budget: u64) -> Result<Check>;
}

pub struct Session {
    backend: Box<dyn Backend>,
    generation: u64,
    graph: Graph,
    free_bound: BTreeMap<u64, BTreeSet<String>>,
    enum_names: BTreeMap<String, Vec<String>>,
    bound_sorts: BTreeMap<String, Sort>,
    checks: u64,
    retired: bool,
}

impl Session {
    pub fn new(backend: &str, z3_library: Option<&str>) -> Result<Self> {
        let backend: Box<dyn Backend> = match backend {
            "z3" => Box::new(z3::Z3::new(z3_library
                .ok_or_else(|| Fault::invalid("--z3-library is required for the Z3 backend"))?)?),
            "oxiz" => Box::new(oxiz::Oxiz::new()),
            _ => return Err(Fault::invalid("--backend must be z3 or oxiz")),
        };
        Ok(Self { backend, generation: 0, graph: Graph::new(), free_bound: BTreeMap::new(),
            enum_names: BTreeMap::new(), bound_sorts: BTreeMap::new(), checks: 0, retired: false })
    }
    fn identity(&self) -> Vec<(&'static str, Term)> {
        vec![("ok", wire::atom("true")), ("protocol", wire::integer(1)),
            ("generation", wire::integer(self.generation)),
            ("backend", wire::map([("name", wire::binary(self.backend.name())),
                                  ("version", wire::binary(&self.backend.version()))]))]
    }
    pub fn refuse(&mut self, error: Fault) -> Term {
        self.retired = true;
        let mut fields = self.identity();
        fields[0] = ("ok", wire::atom("false"));
        fields.extend([("status", wire::atom(if error.kind == "unsupported" { "unsupported" } else { "error" })), ("error", wire::binary(&error.message)),
            ("why", wire::map([("kind", wire::atom(error.kind)), ("message", wire::binary(&error.message))]))]);
        wire::map(fields)
    }
    pub fn handle(&mut self, request: &Term) -> Term {
        match self.handle_inner(request) {
            Ok(reply) => reply,
            Err(error) => self.refuse(error),
        }
    }
    fn current_generation(&self, value: &Term) -> Result<()> {
        if wire::unsigned(value)? != self.generation {
            Err(Fault::invalid("stale solver generation"))
        } else { Ok(()) }
    }
    fn register_sort(&mut self, sort: &Sort) -> Result<()> {
        match sort {
            Sort::Enum(name, variants) => {
                if self.enum_names.get(name).is_some_and(|old| old != variants) {
                    return Err(Fault::invalid(format!("enum {name} was redeclared differently")));
                }
                self.enum_names.insert(name.clone(), variants.clone());
            }
            Sort::Array(key, value) => { self.register_sort(key)?; self.register_sort(value)?; }
            Sort::Seq(element) => self.register_sort(element)?,
            _ => {}
        }
        Ok(())
    }
    fn import(&mut self, values: &Term) -> Result<()> {
        let values = wire::items(values)?;
        if values.len() > 32768 { return Err(Fault::invalid("too many nodes in one import")); }
        for value in values.iter() {
            let node = Node::parse(value)?;
            if let Some(previous) = self.graph.get(&node.id) {
                if previous != &node { return Err(Fault::invalid(format!("DAG ID {} was redefined", node.id))); }
                continue;
            }
            if self.graph.len() >= 100_000 { return Err(Fault::invalid("DAG exceeds 100000 nodes")); }
            node.validate(&self.graph)?;
            self.register_sort(&node.sort)?;
            let mut free = BTreeSet::new();
            for arg in &node.args { free.extend(self.free_bound[arg].iter().cloned()); }
            if node.op == "bound" {
                let name = wire::binary_text(&node.data)?.to_owned();
                if self.bound_sorts.get(&name).is_some_and(|sort| sort != &node.sort) {
                    return Err(Fault::invalid("bound name has inconsistent sorts"));
                }
                self.bound_sorts.insert(name.clone(), node.sort.clone());
                free.insert(name);
            }
            if node.op == "forall" || node.op == "exists" {
                for (name, sort) in node.binders()? {
                    if self.bound_sorts.get(&name).is_some_and(|old| old != &sort) {
                        return Err(Fault::invalid("binder sort differs from its bound node"));
                    }
                    self.bound_sorts.insert(name.clone(), sort);
                    free.remove(&name);
                }
            }
            self.backend.import(&node, &self.graph)?;
            self.free_bound.insert(node.id, free);
            self.graph.insert(node.id, node);
        }
        Ok(())
    }
    fn closed(&self, id: u64, boolean: bool) -> Result<()> {
        let node = self.graph.get(&id).ok_or_else(|| Fault::invalid(format!("unknown DAG ID {id}")))?;
        if boolean && node.sort != Sort::Bool { return Err(Fault::invalid("assertions/assumptions must be Boolean")); }
        if !self.free_bound[&id].is_empty() { return Err(Fault::invalid("free bound node escaped its quantifier")); }
        Ok(())
    }
    fn assertions(&mut self, values: &Term) -> Result<()> {
        for value in wire::items(values)?.iter() {
            let parts = wire::items(value)?;
            if parts.len() != 2 { return Err(Fault::invalid("assertion needs label and node ID")); }
            let label = wire::binary_text(&parts[0])?;
            let id = wire::unsigned(&parts[1])?;
            self.closed(id, true)?;
            self.backend.assert(id, label)?;
        }
        Ok(())
    }
    fn check(&mut self, assumptions: &Term, observations: &Term, budget: &Term) -> Result<Term> {
        let budget = wire::unsigned(budget)?;
        if budget == 0 || budget > 10000 { return Err(Fault::invalid("solver budget must be 1..10000ms")); }
        let assumptions = wire::items(assumptions)?.iter().map(wire::unsigned).collect::<Result<Vec<_>>>()?;
        for id in &assumptions { self.closed(*id, true)?; }
        let mut observed = Vec::new();
        let mut labels = BTreeSet::new();
        for value in wire::items(observations)?.iter() {
            let pair = wire::items(value)?;
            if pair.len() != 2 { return Err(Fault::invalid("observation needs label and term ID")); }
            let label = wire::binary_text(&pair[0])?.to_owned();
            if !labels.insert(label.clone()) { return Err(Fault::invalid("duplicate observation label")); }
            let id = wire::unsigned(&pair[1])?;
            self.closed(id, false)?;
            observed.push((label, id));
        }
        let result = self.backend.check(&assumptions, &observed, budget)?;
        self.checks += 1;
        let unavailable = result.observations.iter().filter(|(_, value)| {
            wire::items(value).ok().and_then(|items| items.first().and_then(|v| wire::text(v).ok()).map(str::to_owned))
                .is_some_and(|tag| tag == "opaque" || tag == "unavailable")
        }).count();
        let model_status = if result.status != "sat" { "unavailable" }
            else if unavailable == 0 { "available" }
            else if unavailable == result.observations.len() { "unavailable" }
            else { "partial" };
        let mut fields = self.identity();
        fields.extend([
            ("status", wire::atom(result.status)),
            ("observations", wire::list(result.observations.into_iter().map(|(name, value)| wire::list([wire::binary(&name), value])))),
            ("model-status", wire::atom(model_status)),
            ("core", wire::list(result.core.iter().map(|name| wire::binary(name)))),
            ("core-kind", wire::atom(result.core_kind)),
            ("why", wire::map([("kind", wire::atom(result.reason_kind)), ("message", wire::binary(&result.reason))])),
            ("stats", wire::map([("solve-us", wire::integer(result.solve_us)),
                ("nodes", wire::integer(self.graph.len())), ("checks", wire::integer(self.checks))])),
        ]);
        Ok(wire::map(fields))
    }
    fn handle_inner(&mut self, request: &Term) -> Result<Term> {
        let parts = wire::tuple(request)?;
        let op = wire::text(parts.first().ok_or_else(|| Fault::invalid("empty request"))?)?;
        if op == "hello" && parts.len() == 1 {
            let mut fields = self.identity();
            fields.push(("capabilities", self.backend.capabilities()));
            fields.push(("pid", wire::integer(std::process::id())));
            return Ok(wire::map(fields));
        }
        if parts.len() < 2 { return Err(Fault::invalid("request lacks generation")); }
        self.current_generation(&parts[1])?;
        if op == "reset" && parts.len() == 2 {
            self.backend.reset()?;
            self.generation = self.generation.checked_add(1).ok_or_else(|| Fault::invalid("generation exhausted"))?;
            self.graph.clear(); self.free_bound.clear(); self.enum_names.clear(); self.bound_sorts.clear(); self.checks = 0; self.retired = false;
            return Ok(wire::map(self.identity()));
        }
        if self.retired { return Err(Fault::invalid("solver conversation is retired")); }
        match (op, parts.len()) {
            ("load", 4) => {
                self.import(&parts[2])?; self.assertions(&parts[3])?;
                let mut fields = self.identity();
                fields.push(("stats", wire::map([("nodes", wire::integer(self.graph.len())), ("checks", wire::integer(self.checks))])));
                Ok(wire::map(fields))
            }
            ("check", 5) => self.check(&parts[2], &parts[3], &parts[4]),
            ("scope", 7) => {
                self.import(&parts[2])?;
                self.backend.push()?;
                let result = (|| { self.assertions(&parts[3])?; self.check(&parts[4], &parts[5], &parts[6]) })();
                let cleanup = self.backend.pop();
                match result { Ok(reply) => { cleanup?; Ok(reply) }, Err(error) => Err(error) }
            }
            _ => Err(Fault::invalid(format!("unknown request or arity: {op}"))),
        }
    }
}
