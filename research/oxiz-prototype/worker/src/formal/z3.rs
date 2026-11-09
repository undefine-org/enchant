//! A deliberately thin C-API adapter to the explicitly pinned libz3. All
//! expressions are constructed by native functions; none are scripts.
#![allow(non_snake_case)]

use super::{Backend, Check};
use super::dag::{Graph, Node, Sort, ALL_OPS};
use super::wire::{self, Fault, Result};
use eetf::Term;
use libloading::Library;
use num_bigint::BigInt;
use num_rational::BigRational;
use num_traits::{One, Zero};
use std::collections::HashMap;
use std::ffi::{CStr, CString, c_char, c_void};
use std::ptr;
use std::time::Instant;

type H = *mut c_void;
type Unary = unsafe extern "C" fn(H, H) -> H;
type Binary = unsafe extern "C" fn(H, H, H) -> H;
type Ternary = unsafe extern "C" fn(H, H, H, H) -> H;
type Nary = unsafe extern "C" fn(H, u32, *const H) -> H;
type Nullary = unsafe extern "C" fn(H) -> H;

macro_rules! api {
    ($($name:ident: $signature:ty),+ $(,)?) => {
        struct Api { _library: Library, $( $name: $signature, )+ }
        impl Api {
            fn load(path: &str) -> Result<Self> {
                // Only the caller-selected local artifact is loaded. No PATH
                // lookup or loader fallback can select another solver.
                let library = unsafe { Library::new(path) }
                    .map_err(|e| Fault::backend(format!("cannot load pinned libz3: {e}")))?;
                $(let $name = unsafe { *library.get::<$signature>(concat!(stringify!($name), "\0").as_bytes())
                    .map_err(|e| Fault::backend(format!("libz3 lacks {}: {e}", stringify!($name))))? };)+
                Ok(Self { _library: library, $( $name, )+ })
            }
        }
    };
}

api! {
    Z3_mk_config: unsafe extern "C" fn() -> H,
    Z3_del_config: unsafe extern "C" fn(H),
    Z3_mk_context: unsafe extern "C" fn(H) -> H,
    Z3_del_context: unsafe extern "C" fn(H),
    Z3_set_error_handler: unsafe extern "C" fn(H, Option<unsafe extern "C" fn(H, u32)>),
    Z3_get_error_code: unsafe extern "C" fn(H) -> u32,
    Z3_get_error_msg: unsafe extern "C" fn(H, u32) -> *const c_char,
    Z3_get_version: unsafe extern "C" fn(*mut u32,*mut u32,*mut u32,*mut u32),
    Z3_mk_string_symbol: unsafe extern "C" fn(H, *const c_char) -> H,
    Z3_mk_bool_sort: Nullary,
    Z3_mk_int_sort: Nullary,
    Z3_mk_real_sort: Nullary,
    Z3_mk_string_sort: Nullary,
    Z3_mk_bv_sort: unsafe extern "C" fn(H,u32) -> H,
    Z3_mk_fpa_sort: unsafe extern "C" fn(H,u32,u32) -> H,
    Z3_mk_fpa_rounding_mode_sort: Nullary,
    Z3_mk_array_sort: Binary,
    Z3_mk_seq_sort: Unary,
    Z3_mk_uninterpreted_sort: Unary,
    Z3_mk_enumeration_sort: unsafe extern "C" fn(H,H,u32,*const H,*mut H,*mut H) -> H,
    Z3_mk_const: Binary,
    Z3_mk_fresh_const: unsafe extern "C" fn(H,*const c_char,H) -> H,
    Z3_mk_func_decl: unsafe extern "C" fn(H,H,u32,*const H,H) -> H,
    Z3_mk_app: unsafe extern "C" fn(H,H,u32,*const H) -> H,
    Z3_mk_true: Nullary,
    Z3_mk_false: Nullary,
    Z3_mk_numeral: unsafe extern "C" fn(H,*const c_char,H) -> H,
    Z3_mk_u32string: unsafe extern "C" fn(H,u32,*const u32) -> H,
    Z3_mk_not: Unary,
    Z3_mk_and: Nary,
    Z3_mk_or: Nary,
    Z3_mk_eq: Binary,
    Z3_mk_distinct: Nary,
    Z3_mk_implies: Binary,
    Z3_mk_xor: Binary,
    Z3_mk_ite: Ternary,
    Z3_mk_add: Nary,
    Z3_mk_mul: Nary,
    Z3_mk_sub: Nary,
    Z3_mk_unary_minus: Unary,
    Z3_mk_div: Binary,
    Z3_mk_mod: Binary,
    Z3_mk_lt: Binary,
    Z3_mk_le: Binary,
    Z3_mk_gt: Binary,
    Z3_mk_ge: Binary,
    Z3_mk_int2real: Unary,
    Z3_mk_real2int: Unary,
    Z3_mk_is_int: Unary,
    Z3_mk_const_array: Binary,
    Z3_mk_select: Binary,
    Z3_mk_store: Ternary,
    Z3_mk_seq_concat: Nary,
    Z3_mk_seq_length: Unary,
    Z3_mk_seq_contains: Binary,
    Z3_mk_seq_prefix: Binary,
    Z3_mk_seq_suffix: Binary,
    Z3_mk_seq_at: Binary,
    Z3_mk_seq_extract: Ternary,
    Z3_mk_seq_index: Ternary,
    Z3_mk_seq_replace: Ternary,
    Z3_mk_seq_empty: Unary,
    Z3_mk_seq_unit: Unary,
    Z3_mk_seq_nth: Binary,
    Z3_mk_bvadd: Binary,
    Z3_mk_bvsub: Binary,
    Z3_mk_bvmul: Binary,
    Z3_mk_bvand: Binary,
    Z3_mk_bvor: Binary,
    Z3_mk_bvxor: Binary,
    Z3_mk_bvnot: Unary,
    Z3_mk_bvneg: Unary,
    Z3_mk_bvshl: Binary,
    Z3_mk_bvlshr: Binary,
    Z3_mk_bvashr: Binary,
    Z3_mk_bvult: Binary,
    Z3_mk_bvule: Binary,
    Z3_mk_bvslt: Binary,
    Z3_mk_bvsle: Binary,
    Z3_mk_concat: Binary,
    Z3_mk_extract: unsafe extern "C" fn(H,u32,u32,H) -> H,
    Z3_mk_zero_ext: unsafe extern "C" fn(H,u32,H) -> H,
    Z3_mk_sign_ext: unsafe extern "C" fn(H,u32,H) -> H,
    Z3_mk_forall_const: unsafe extern "C" fn(H,u32,u32,*const H,u32,*const H,H) -> H,
    Z3_mk_exists_const: unsafe extern "C" fn(H,u32,u32,*const H,u32,*const H,H) -> H,
    Z3_mk_fpa_rne: Nullary,
    Z3_mk_fpa_rna: Nullary,
    Z3_mk_fpa_rtp: Nullary,
    Z3_mk_fpa_rtn: Nullary,
    Z3_mk_fpa_rtz: Nullary,
    Z3_mk_fpa_to_fp_bv: Binary,
    Z3_mk_fpa_to_ieee_bv: Unary,
    Z3_mk_fpa_add: Ternary,
    Z3_mk_fpa_sub: Ternary,
    Z3_mk_fpa_mul: Ternary,
    Z3_mk_fpa_div: Ternary,
    Z3_mk_fpa_neg: Unary,
    Z3_mk_fpa_eq: Binary,
    Z3_mk_fpa_lt: Binary,
    Z3_mk_fpa_leq: Binary,
    Z3_mk_fpa_is_nan: Unary,
    Z3_mk_fpa_is_infinite: Unary,
    Z3_mk_solver: Nullary,
    Z3_solver_inc_ref: unsafe extern "C" fn(H,H),
    Z3_solver_dec_ref: unsafe extern "C" fn(H,H),
    Z3_solver_assert: unsafe extern "C" fn(H,H,H),
    Z3_solver_assert_and_track: unsafe extern "C" fn(H,H,H,H),
    Z3_solver_push: unsafe extern "C" fn(H,H),
    Z3_solver_pop: unsafe extern "C" fn(H,H,u32),
    Z3_solver_check: unsafe extern "C" fn(H,H) -> i32,
    Z3_solver_check_assumptions: unsafe extern "C" fn(H,H,u32,*const H) -> i32,
    Z3_solver_get_model: Unary,
    Z3_solver_get_reason_unknown: unsafe extern "C" fn(H,H) -> *const c_char,
    Z3_solver_get_unsat_core: Unary,
    Z3_ast_vector_inc_ref: unsafe extern "C" fn(H,H),
    Z3_ast_vector_dec_ref: unsafe extern "C" fn(H,H),
    Z3_ast_vector_size: unsafe extern "C" fn(H,H) -> u32,
    Z3_ast_vector_get: unsafe extern "C" fn(H,H,u32) -> H,
    Z3_get_ast_id: unsafe extern "C" fn(H,H) -> u32,
    Z3_mk_params: Nullary,
    Z3_params_inc_ref: unsafe extern "C" fn(H,H),
    Z3_params_dec_ref: unsafe extern "C" fn(H,H),
    Z3_params_set_uint: unsafe extern "C" fn(H,H,H,u32),
    Z3_solver_set_params: unsafe extern "C" fn(H,H,H),
    Z3_model_inc_ref: unsafe extern "C" fn(H,H),
    Z3_model_dec_ref: unsafe extern "C" fn(H,H),
    Z3_model_eval: unsafe extern "C" fn(H,H,H,bool,*mut H) -> bool,
    Z3_get_bool_value: unsafe extern "C" fn(H,H) -> i32,
    Z3_is_numeral_ast: unsafe extern "C" fn(H,H) -> bool,
    Z3_get_numeral_string: unsafe extern "C" fn(H,H) -> *const c_char,
    Z3_is_string: unsafe extern "C" fn(H,H) -> bool,
    Z3_get_string_length: unsafe extern "C" fn(H,H) -> u32,
    Z3_get_string_contents: unsafe extern "C" fn(H,H,u32,*mut u32),
    Z3_get_ast_kind: unsafe extern "C" fn(H,H) -> u32,
    Z3_get_app_decl: Unary,
}

pub struct Z3 {
    api: Api,
    context: H,
    solver: H,
    terms: HashMap<u64,H>,
    term_sorts: HashMap<u64,Sort>,
    sorts: HashMap<Sort,H>,
    functions: HashMap<String,(Vec<Sort>,Sort,H)>,
    enum_ctors: HashMap<Sort,Vec<H>>,
    enum_values: HashMap<H,(String,String)>,
    tracked: Vec<(u32,String)>,
    scopes: Vec<usize>,
}

unsafe extern "C" fn error_handler(_context: H, _error: u32) {}

fn cstring(value: &str) -> Result<CString> {
    CString::new(value).map_err(|_| Fault::invalid("a native symbol contains NUL"))
}
fn borrowed_string(value: *const c_char) -> String {
    if value.is_null() { String::new() }
    else { unsafe { CStr::from_ptr(value) }.to_string_lossy().into_owned() }
}

impl Z3 {
    pub fn new(path: &str) -> Result<Self> {
        if !std::path::Path::new(path).is_absolute() { return Err(Fault::invalid("libz3 path must be absolute")); }
        let api = Api::load(path)?;
        let mut result = Self { api, context: ptr::null_mut(), solver: ptr::null_mut(),
            terms: HashMap::new(), term_sorts: HashMap::new(), sorts: HashMap::new(), functions: HashMap::new(),
            enum_ctors: HashMap::new(), enum_values: HashMap::new(), tracked: vec![], scopes: vec![] };
        result.initialize()?;
        Ok(result)
    }
    fn initialize(&mut self) -> Result<()> {
        unsafe {
            let config = (self.api.Z3_mk_config)();
            self.context = (self.api.Z3_mk_context)(config);
            (self.api.Z3_del_config)(config);
            if self.context.is_null() { return Err(Fault::backend("Z3 context allocation failed")); }
            (self.api.Z3_set_error_handler)(self.context,Some(error_handler));
            self.solver = (self.api.Z3_mk_solver)(self.context);
            self.checked(self.solver)?;
            (self.api.Z3_solver_inc_ref)(self.context,self.solver);
        }
        self.check_error()
    }
    fn destroy(&mut self) {
        unsafe {
            if !self.context.is_null() {
                if !self.solver.is_null() { (self.api.Z3_solver_dec_ref)(self.context,self.solver); }
                (self.api.Z3_del_context)(self.context);
            }
        }
        self.context = ptr::null_mut(); self.solver = ptr::null_mut();
    }
    fn check_error(&self) -> Result<()> {
        let code = unsafe { (self.api.Z3_get_error_code)(self.context) };
        if code == 0 { Ok(()) } else {
            Err(Fault::backend(format!("Z3 native API: {}",borrowed_string(unsafe { (self.api.Z3_get_error_msg)(self.context,code) }))))
        }
    }
    fn checked(&self, value: H) -> Result<H> {
        self.check_error()?;
        if value.is_null() { Err(Fault::backend("Z3 native constructor returned null")) } else { Ok(value) }
    }
    fn symbol(&self, value: &str) -> Result<H> {
        let value = cstring(value)?;
        self.checked(unsafe { (self.api.Z3_mk_string_symbol)(self.context,value.as_ptr()) })
    }
    fn variable_name(bound: bool, name: &str) -> String {
        format!("formal.{}.{}",if bound { "bound" } else { "var" },name)
    }
    fn numeral(&self, value: &str, sort: H) -> Result<H> {
        let value = cstring(value)?;
        self.checked(unsafe { (self.api.Z3_mk_numeral)(self.context,value.as_ptr(),sort) })
    }
    fn sort(&mut self, sort: &Sort) -> Result<H> {
        if let Some(native) = self.sorts.get(sort) { return Ok(*native); }
        let c = self.context;
        let native = unsafe { match sort {
            Sort::Bool => (self.api.Z3_mk_bool_sort)(c), Sort::Int => (self.api.Z3_mk_int_sort)(c),
            Sort::Real => (self.api.Z3_mk_real_sort)(c), Sort::String => (self.api.Z3_mk_string_sort)(c),
            Sort::Bv(width) => (self.api.Z3_mk_bv_sort)(c,*width),
            Sort::Fp(eb,sb) => (self.api.Z3_mk_fpa_sort)(c,*eb,*sb),
            Sort::Rounding => (self.api.Z3_mk_fpa_rounding_mode_sort)(c),
            Sort::Array(key,value) => { let key = self.sort(key)?; let value = self.sort(value)?; (self.api.Z3_mk_array_sort)(c,key,value) }
            Sort::Seq(element) => { let element = self.sort(element)?; (self.api.Z3_mk_seq_sort)(c,element) }
            Sort::Uninterpreted(name) => { let name = self.symbol(&format!("formal.sort.{name}"))?; (self.api.Z3_mk_uninterpreted_sort)(c,name) }
            Sort::Enum(name,variants) => {
                let name_symbol = self.symbol(&format!("formal.enum.{name}"))?;
                let symbols = variants.iter().enumerate().map(|(i,variant)| self.symbol(&format!("formal.enum.{name}.{i}.{variant}"))).collect::<Result<Vec<_>>>()?;
                let mut ctors = vec![ptr::null_mut(); variants.len()];
                let mut testers = vec![ptr::null_mut(); variants.len()];
                let result = (self.api.Z3_mk_enumeration_sort)(c,name_symbol,variants.len() as u32,symbols.as_ptr(),ctors.as_mut_ptr(),testers.as_mut_ptr());
                self.checked(result)?;
                for (ctor,variant) in ctors.iter().zip(variants) { self.enum_values.insert(*ctor,(name.clone(),variant.clone())); }
                self.enum_ctors.insert(sort.clone(),ctors);
                result
            }
        }};
        self.checked(native)?;
        self.sorts.insert(sort.clone(),native);
        Ok(native)
    }
    fn term(&self, id: u64) -> Result<H> {
        self.terms.get(&id).copied().ok_or_else(|| Fault::invalid(format!("native term {id} is missing")))
    }
    fn apply_nary(&self, function: Nary, args: &[H]) -> Result<H> {
        self.checked(unsafe { function(self.context,args.len() as u32,args.as_ptr()) })
    }
    fn empty_text(&self) -> Result<H> {
        self.checked(unsafe { (self.api.Z3_mk_u32string)(self.context,0,ptr::null()) })
    }
    fn eval(&self, model: H, expression: H) -> Option<H> {
        let mut value = ptr::null_mut();
        // Complete only don't-care symbols in the already returned SAT
        // model. This chooses a concrete extension for independent replay;
        // it neither changes solver status nor asserts uniqueness.
        if unsafe { (self.api.Z3_model_eval)(self.context,model,expression,true,&mut value) } && !value.is_null() {
            Some(value)
        } else { None }
    }
    fn observe(&self, model: H, id: u64) -> Term {
        let Some(expression) = self.terms.get(&id).copied() else {
            return wire::tagged("unavailable",[wire::binary("missing native observation term")]);
        };
        let Some(value) = self.eval(model,expression) else {
            return wire::tagged("unavailable",[wire::binary("Z3 did not evaluate the requested term")]);
        };
        self.value(model,value,&self.term_sorts[&id])
    }
    fn value(&self, model: H, value: H, sort: &Sort) -> Term {
        let c = self.context;
        let opaque = |reason: &str| wire::tagged("opaque",[wire::binary(reason)]);
        match sort {
            Sort::Bool => match unsafe { (self.api.Z3_get_bool_value)(c,value) } {
                1 => wire::tagged("bool",[wire::atom("true")]),
                -1 => wire::tagged("bool",[wire::atom("false")]),
                _ => opaque("Z3 Boolean observation is not concrete"),
            }
            Sort::Int | Sort::Real | Sort::Bv(_) => {
                if !unsafe { (self.api.Z3_is_numeral_ast)(c,value) } { return opaque("Z3 numeric observation is not a rational numeral"); }
                let numeral = borrowed_string(unsafe { (self.api.Z3_get_numeral_string)(c,value) });
                let mut pieces = numeral.split('/');
                let Some(numerator) = pieces.next().and_then(|n| n.parse::<BigInt>().ok()) else { return opaque("Z3 numeric constructor returned a non-integer component"); };
                let denominator = match pieces.next() {
                    Some(denominator) => match denominator.parse::<BigInt>() { Ok(d) if !d.is_zero() => d, _ => return opaque("invalid rational denominator") },
                    None => BigInt::one(),
                };
                if pieces.next().is_some() { return opaque("numeric value has unsupported components"); }
                match sort {
                    Sort::Real => wire::tagged("real",[wire::integer(numerator),wire::integer(denominator)]),
                    Sort::Int if denominator.is_one() => wire::tagged("int",[wire::integer(numerator)]),
                    Sort::Bv(width) if denominator.is_one() => wire::tagged("bv",[wire::integer(*width),wire::integer(numerator)]),
                    _ => opaque("numeric observation sort differs from its value"),
                }
            }
            Sort::String => {
                if !unsafe { (self.api.Z3_is_string)(c,value) } { return opaque("Z3 string observation is not concrete"); }
                let length = unsafe { (self.api.Z3_get_string_length)(c,value) } as usize;
                if length > wire::MAX_PACKET / 4 { return opaque("observed text exceeds response capacity"); }
                let mut codepoints = vec![0u32;length];
                unsafe { (self.api.Z3_get_string_contents)(c,value,length as u32,codepoints.as_mut_ptr()); }
                let text = codepoints.into_iter().map(char::from_u32).collect::<Option<String>>();
                match text { Some(text) => wire::tagged("text",[wire::binary(&text)]), None => opaque("model string contains a non-Unicode scalar") }
            }
            Sort::Enum(_,_) => {
                if unsafe { (self.api.Z3_get_ast_kind)(c,value) } != 1 { return opaque("enum observation is not a constructor application"); }
                let declaration = unsafe { (self.api.Z3_get_app_decl)(c,value) };
                match self.enum_values.get(&declaration) {
                    Some((name,constructor)) => wire::tagged("enum",[wire::binary(name),wire::binary(constructor)]),
                    None => opaque("unrecognized enum constructor"),
                }
            }
            Sort::Fp(eb,sb) => {
                let is_nan = unsafe { (self.api.Z3_mk_fpa_is_nan)(c,value) };
                if self.eval(model,is_nan).is_some_and(|v| unsafe { (self.api.Z3_get_bool_value)(c,v) } == 1) {
                    return opaque("SMT FP NaN has no stable IEEE payload identity");
                }
                let bits_term = unsafe { (self.api.Z3_mk_fpa_to_ieee_bv)(c,value) };
                let Some(bits) = self.eval(model,bits_term) else { return opaque("FP observation has no concrete IEEE encoding"); };
                if !unsafe { (self.api.Z3_is_numeral_ast)(c,bits) } { return opaque("FP encoding is not concrete"); }
                let bits = borrowed_string(unsafe { (self.api.Z3_get_numeral_string)(c,bits) });
                match bits.parse::<BigInt>() {
                    Ok(bits) => wire::tagged("fp",[wire::integer(*eb),wire::integer(*sb),wire::integer(bits)]),
                    Err(_) => opaque("FP encoding is not an unsigned numeral"),
                }
            }
            Sort::Array(_,_) => opaque("full array materialization is not exposed; observe scalar selects"),
            Sort::Seq(_) => opaque("full sequence materialization is not exposed; observe length and elements"),
            Sort::Uninterpreted(_) => opaque("uninterpreted model representatives are model-local; observe relations"),
            Sort::Rounding => opaque("rounding-mode model materialization is not exposed"),
        }
    }
}

impl Drop for Z3 { fn drop(&mut self) { self.destroy(); } }

impl Backend for Z3 {
    fn name(&self) -> &'static str { "z3" }
    fn version(&self) -> String {
        let (mut major,mut minor,mut build,mut revision) = (0,0,0,0);
        unsafe { (self.api.Z3_get_version)(&mut major,&mut minor,&mut build,&mut revision); }
        if revision == 0 { format!("{major}.{minor}.{build}") } else { format!("{major}.{minor}.{build}.{revision}") }
    }
    fn capabilities(&self) -> Term {
        wire::map([
            ("operations",wire::list(ALL_OPS.iter().map(|op| wire::binary(op)))),
            ("sorts",wire::list(["bool","int","real","string","bv","fp","rounding","array","seq","uninterpreted","enum"].into_iter().map(wire::binary))),
            ("limits",wire::binary_map([
                ("max-bv-width",wire::integer(4096)),("max-fp-bits",wire::integer(128)),
                ("real-literal-bits",wire::binary("arbitrary")),("symbolic-rounding",wire::atom("true")),
                ("native-cores",wire::atom("true")),("max-text-codepoint",wire::integer(0x2ffff)),
                ("model-completion",wire::binary("concrete-extension")),
                ("model",wire::binary("observed scalars and enum constructors; select/nth for collections")),
            ])),
        ])
    }
    fn reset(&mut self) -> Result<()> {
        self.destroy(); self.terms.clear(); self.term_sorts.clear(); self.sorts.clear();
        self.functions.clear(); self.enum_ctors.clear(); self.enum_values.clear(); self.tracked.clear(); self.scopes.clear();
        self.initialize()
    }
    fn import(&mut self, node: &Node, _graph: &Graph) -> Result<()> {
        let c = self.context;
        let sort = self.sort(&node.sort)?;
        let args = node.args.iter().map(|id| self.term(*id)).collect::<Result<Vec<_>>>()?;
        let result = unsafe { match node.op.as_str() {
            "var" | "bound" => {
                let name = Self::variable_name(node.op == "bound",wire::binary_text(&node.data)?);
                let symbol = self.symbol(&name)?;
                (self.api.Z3_mk_const)(c,symbol,sort)
            }
            "bool" => if wire::boolean(&node.data)? { (self.api.Z3_mk_true)(c) } else { (self.api.Z3_mk_false)(c) },
            "int" => self.numeral(&wire::number(&node.data)?.to_string(),sort)?,
            "real" => {
                let pair = wire::items(&node.data)?;
                let rational = BigRational::new(wire::number(&pair[0])?,wire::number(&pair[1])?);
                self.numeral(&format!("{}/{}",rational.numer(),rational.denom()),sort)?
            }
            "text" => {
                let chars = wire::binary_text(&node.data)?.chars().map(u32::from).collect::<Vec<_>>();
                (self.api.Z3_mk_u32string)(c,chars.len() as u32,chars.as_ptr())
            }
            "bv" => {
                let Sort::Bv(width) = node.sort else { unreachable!() };
                let modulus = BigInt::one() << width;
                let bits = wire::number(&node.data)?;
                self.numeral(&(((bits % &modulus)+&modulus)%&modulus).to_string(),sort)?
            }
            "rounding" => match wire::binary_text(&node.data)? {
                "RNE" => (self.api.Z3_mk_fpa_rne)(c),"RNA" => (self.api.Z3_mk_fpa_rna)(c),
                "RTP" => (self.api.Z3_mk_fpa_rtp)(c),"RTN" => (self.api.Z3_mk_fpa_rtn)(c),
                "RTZ" => (self.api.Z3_mk_fpa_rtz)(c),_ => unreachable!(),
            }
            "enum" => {
                let Sort::Enum(_,variants) = &node.sort else { unreachable!() };
                let constructor = wire::binary_text(&node.data)?;
                let index = variants.iter().position(|v| v == constructor).ok_or_else(|| Fault::invalid("unknown enum constructor"))?;
                let declaration = self.enum_ctors[&node.sort][index];
                (self.api.Z3_mk_app)(c,declaration,0,ptr::null())
            }
            "not" => (self.api.Z3_mk_not)(c,args[0]),
            "and" => self.apply_nary(self.api.Z3_mk_and,&args)?,"or" => self.apply_nary(self.api.Z3_mk_or,&args)?,
            "implies" => (self.api.Z3_mk_implies)(c,args[0],args[1]),"xor" => (self.api.Z3_mk_xor)(c,args[0],args[1]),
            "eq" => {
                let terms = args.windows(2).map(|p| self.checked((self.api.Z3_mk_eq)(c,p[0],p[1]))).collect::<Result<Vec<_>>>()?;
                self.apply_nary(self.api.Z3_mk_and,&terms)?
            }
            "distinct" => self.apply_nary(self.api.Z3_mk_distinct,&args)?,
            "ite" => (self.api.Z3_mk_ite)(c,args[0],args[1],args[2]),
            "add" | "mul" if args.is_empty() => self.numeral(if node.op == "add" { "0" } else { "1" },sort)?,
            "add" => self.apply_nary(self.api.Z3_mk_add,&args)?,"mul" => self.apply_nary(self.api.Z3_mk_mul,&args)?,
            "sub" => self.apply_nary(self.api.Z3_mk_sub,&args)?,"neg" => (self.api.Z3_mk_unary_minus)(c,args[0]),
            "div" => (self.api.Z3_mk_div)(c,args[0],args[1]),"mod" => (self.api.Z3_mk_mod)(c,args[0],args[1]),
            "lt" => (self.api.Z3_mk_lt)(c,args[0],args[1]),"le" => (self.api.Z3_mk_le)(c,args[0],args[1]),
            "gt" => (self.api.Z3_mk_gt)(c,args[0],args[1]),"ge" => (self.api.Z3_mk_ge)(c,args[0],args[1]),
            "to-real" => (self.api.Z3_mk_int2real)(c,args[0]),"to-int" => (self.api.Z3_mk_real2int)(c,args[0]),"is-int" => (self.api.Z3_mk_is_int)(c,args[0]),
            "array-const" => { let Sort::Array(key,_) = &node.sort else { unreachable!() }; let key = self.sort(key)?; (self.api.Z3_mk_const_array)(c,key,args[0]) }
            "select" => (self.api.Z3_mk_select)(c,args[0],args[1]),"store" => (self.api.Z3_mk_store)(c,args[0],args[1],args[2]),
            "str-concat" if args.is_empty() => self.empty_text()?,
            "str-concat" | "seq-concat" if args.len() == 1 => args[0],
            "str-concat" | "seq-concat" if !args.is_empty() => self.apply_nary(self.api.Z3_mk_seq_concat,&args)?,
            "str-len" | "seq-len" => (self.api.Z3_mk_seq_length)(c,args[0]),
            "str-contains" => (self.api.Z3_mk_seq_contains)(c,args[0],args[1]),
            "str-prefix" => (self.api.Z3_mk_seq_prefix)(c,args[0],args[1]),"str-suffix" => (self.api.Z3_mk_seq_suffix)(c,args[0],args[1]),
            "str-at" => (self.api.Z3_mk_seq_at)(c,args[0],args[1]),
            "str-substr" | "seq-extract" => (self.api.Z3_mk_seq_extract)(c,args[0],args[1],args[2]),
            "str-index" => (self.api.Z3_mk_seq_index)(c,args[0],args[1],args[2]),
            "str-replace" => (self.api.Z3_mk_seq_replace)(c,args[0],args[1],args[2]),
            "seq-empty" | "seq-concat" => (self.api.Z3_mk_seq_empty)(c,sort),
            "seq-unit" => (self.api.Z3_mk_seq_unit)(c,args[0]),"seq-nth" => (self.api.Z3_mk_seq_nth)(c,args[0],args[1]),
            "bv-add" => (self.api.Z3_mk_bvadd)(c,args[0],args[1]),"bv-sub" => (self.api.Z3_mk_bvsub)(c,args[0],args[1]),
            "bv-mul" => (self.api.Z3_mk_bvmul)(c,args[0],args[1]),"bv-and" => (self.api.Z3_mk_bvand)(c,args[0],args[1]),
            "bv-or" => (self.api.Z3_mk_bvor)(c,args[0],args[1]),"bv-xor" => (self.api.Z3_mk_bvxor)(c,args[0],args[1]),
            "bv-not" => (self.api.Z3_mk_bvnot)(c,args[0]),"bv-neg" => (self.api.Z3_mk_bvneg)(c,args[0]),
            "bv-shl" => (self.api.Z3_mk_bvshl)(c,args[0],args[1]),"bv-lshr" => (self.api.Z3_mk_bvlshr)(c,args[0],args[1]),"bv-ashr" => (self.api.Z3_mk_bvashr)(c,args[0],args[1]),
            "bv-ult" => (self.api.Z3_mk_bvult)(c,args[0],args[1]),"bv-ule" => (self.api.Z3_mk_bvule)(c,args[0],args[1]),
            "bv-slt" => (self.api.Z3_mk_bvslt)(c,args[0],args[1]),"bv-sle" => (self.api.Z3_mk_bvsle)(c,args[0],args[1]),
            "bv-concat" => (self.api.Z3_mk_concat)(c,args[0],args[1]),
            "bv-extract" => { let pair = wire::items(&node.data)?; (self.api.Z3_mk_extract)(c,wire::unsigned(&pair[0])? as u32,wire::unsigned(&pair[1])? as u32,args[0]) }
            "bv-zero-extend" => (self.api.Z3_mk_zero_ext)(c,wire::unsigned(&node.data)? as u32,args[0]),
            "bv-sign-extend" => (self.api.Z3_mk_sign_ext)(c,wire::unsigned(&node.data)? as u32,args[0]),
            "uf" => {
                let name = wire::binary_text(wire::field(&node.data,"name")?)?;
                let domain = wire::items(wire::field(&node.data,"domain")?)?.iter().map(Sort::parse).collect::<Result<Vec<_>>>()?;
                let declaration = if let Some((old_domain,old_range,declaration)) = self.functions.get(name) {
                    if old_domain != &domain || old_range != &node.sort { return Err(Fault::invalid("UF signature was changed")); }
                    *declaration
                } else {
                    let domains = domain.iter().map(|sort| self.sort(sort)).collect::<Result<Vec<_>>>()?;
                    let symbol = self.symbol(&format!("formal.uf.{name}"))?;
                    let declaration = self.checked((self.api.Z3_mk_func_decl)(c,symbol,domains.len() as u32,domains.as_ptr(),sort))?;
                    self.functions.insert(name.to_owned(),(domain,node.sort.clone(),declaration)); declaration
                };
                (self.api.Z3_mk_app)(c,declaration,args.len() as u32,args.as_ptr())
            }
            "forall" | "exists" => {
                let mut bound = Vec::new();
                for (name,sort) in node.binders()? {
                    let sort = self.sort(&sort)?;
                    let symbol = self.symbol(&Self::variable_name(true,&name))?;
                    bound.push(self.checked((self.api.Z3_mk_const)(c,symbol,sort))?);
                }
                if bound.is_empty() { args[0] }
                else if node.op == "forall" { (self.api.Z3_mk_forall_const)(c,0,bound.len() as u32,bound.as_ptr(),0,ptr::null(),args[0]) }
                else { (self.api.Z3_mk_exists_const)(c,0,bound.len() as u32,bound.as_ptr(),0,ptr::null(),args[0]) }
            }
            "fp-bits" => {
                let Sort::Fp(eb,sb) = node.sort else { unreachable!() };
                let bits = wire::number(&node.data)?;
                if bits < BigInt::zero() || bits >= (BigInt::one() << (eb+sb)) { return Err(Fault::invalid("IEEE bit pattern exceeds format")); }
                let bv_sort = self.sort(&Sort::Bv(eb+sb))?;
                let bv = self.numeral(&bits.to_string(),bv_sort)?;
                (self.api.Z3_mk_fpa_to_fp_bv)(c,bv,sort)
            }
            "fp-add" => (self.api.Z3_mk_fpa_add)(c,args[0],args[1],args[2]),"fp-sub" => (self.api.Z3_mk_fpa_sub)(c,args[0],args[1],args[2]),
            "fp-mul" => (self.api.Z3_mk_fpa_mul)(c,args[0],args[1],args[2]),"fp-div" => (self.api.Z3_mk_fpa_div)(c,args[0],args[1],args[2]),
            "fp-neg" => (self.api.Z3_mk_fpa_neg)(c,args[0]),"fp-eq" => (self.api.Z3_mk_fpa_eq)(c,args[0],args[1]),
            "fp-lt" => (self.api.Z3_mk_fpa_lt)(c,args[0],args[1]),"fp-le" => (self.api.Z3_mk_fpa_leq)(c,args[0],args[1]),
            "fp-is-nan" => (self.api.Z3_mk_fpa_is_nan)(c,args[0]),"fp-is-inf" => (self.api.Z3_mk_fpa_is_infinite)(c,args[0]),
            "fp-to-ieee-bv" => (self.api.Z3_mk_fpa_to_ieee_bv)(c,args[0]),
            op => return Err(Fault::unsupported(format!("Z3 native operation {op} is not implemented"))),
        }};
        self.checked(result)?;
        self.terms.insert(node.id,result); self.term_sorts.insert(node.id,node.sort.clone());
        Ok(())
    }
    fn assert(&mut self, id: u64, label: &str) -> Result<()> {
        let expression = self.term(id)?;
        let bool_sort = self.sort(&Sort::Bool)?;
        let prefix = cstring("formal.private.assertion")?;
        let track = self.checked(unsafe { (self.api.Z3_mk_fresh_const)(self.context,prefix.as_ptr(),bool_sort) })?;
        let native_id = unsafe { (self.api.Z3_get_ast_id)(self.context,track) };
        unsafe { (self.api.Z3_solver_assert_and_track)(self.context,self.solver,expression,track); }
        self.check_error()?;
        self.tracked.push((native_id,label.to_owned()));
        Ok(())
    }
    fn push(&mut self) -> Result<()> {
        if self.scopes.len() >= 32 { return Err(Fault::invalid("scope depth exceeds 32")); }
        unsafe { (self.api.Z3_solver_push)(self.context,self.solver); }
        self.check_error()?; self.scopes.push(self.tracked.len()); Ok(())
    }
    fn pop(&mut self) -> Result<()> {
        let count = self.scopes.pop().ok_or_else(|| Fault::invalid("scope underflow"))?;
        unsafe { (self.api.Z3_solver_pop)(self.context,self.solver,1); }
        self.check_error()?; self.tracked.truncate(count); Ok(())
    }
    fn check(&mut self, assumptions: &[u64], observations: &[(String,u64)], budget: u64) -> Result<Check> {
        let c = self.context;
        let params = self.checked(unsafe { (self.api.Z3_mk_params)(c) })?;
        unsafe { (self.api.Z3_params_inc_ref)(c,params); }
        let timeout = self.symbol("timeout")?;
        unsafe {
            (self.api.Z3_params_set_uint)(c,params,timeout,budget as u32);
            (self.api.Z3_solver_set_params)(c,self.solver,params);
            (self.api.Z3_params_dec_ref)(c,params);
        }
        self.check_error()?;
        let assumptions = assumptions.iter().map(|id| self.term(*id)).collect::<Result<Vec<_>>>()?;
        let started = Instant::now();
        let result = unsafe {
            if assumptions.is_empty() { (self.api.Z3_solver_check)(c,self.solver) }
            else { (self.api.Z3_solver_check_assumptions)(c,self.solver,assumptions.len() as u32,assumptions.as_ptr()) }
        };
        let solve_us = started.elapsed().as_micros();
        self.check_error()?;
        let mut values = Vec::new(); let mut core = Vec::new(); let mut reason = String::new();
        if result == 1 {
            let model = unsafe { (self.api.Z3_solver_get_model)(c,self.solver) };
            if model.is_null() {
                values.extend(observations.iter().map(|(label,_)| (label.clone(),wire::tagged("unavailable",[wire::binary("Z3 did not publish a model")]))));
            } else {
                unsafe { (self.api.Z3_model_inc_ref)(c,model); }
                values.extend(observations.iter().map(|(label,id)| (label.clone(),self.observe(model,*id))));
                unsafe { (self.api.Z3_model_dec_ref)(c,model); }
            }
        } else if result == -1 {
            let vector = unsafe { (self.api.Z3_solver_get_unsat_core)(c,self.solver) };
            if !vector.is_null() {
                unsafe { (self.api.Z3_ast_vector_inc_ref)(c,vector); }
                let count = unsafe { (self.api.Z3_ast_vector_size)(c,vector) };
                for index in 0..count {
                    let term = unsafe { (self.api.Z3_ast_vector_get)(c,vector,index) };
                    let id = unsafe { (self.api.Z3_get_ast_id)(c,term) };
                    if let Some((_,label)) = self.tracked.iter().find(|(native,_)| *native == id) { core.push(label.clone()); }
                }
                unsafe { (self.api.Z3_ast_vector_dec_ref)(c,vector); }
            }
        } else { reason = borrowed_string(unsafe { (self.api.Z3_solver_get_reason_unknown)(c,self.solver) }); }
        let reason_kind = match reason.as_str() { "timeout" => "timeout", "canceled" => "canceled", "incomplete" => "incomplete", _ => "unspecified" };
        Ok(Check { status: if result == 1 { "sat" } else if result == -1 { "unsat" } else { "unknown" },
            observations: values, core, core_kind: "native", reason_kind, reason, solve_us })
    }
}
