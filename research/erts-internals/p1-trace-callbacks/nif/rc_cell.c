/*
 * rc_cell -- the smallest honest client of the ERTS resource-cycle API.
 *
 * A cell is an atom-like box: it holds ONE term in its own process-independent
 * env, like beam-lisp's LazyMemo cell holds its state. Everything a cycle
 * collector must get right is here: a term that embeds other cells (or
 * itself), concurrent reads and writes, and a destructor.
 *
 * Runs on stock ERTS too: the cycle API is resolved with dlsym at load. On
 * stock ERTS `rc_cell:api/0` answers `stock` and cycles leak (the baseline).
 *
 * NIFs:
 *   new(Term)        -> Cell           put(Cell, Term) -> ok
 *   get(Cell)        -> Term           live()          -> Count
 *   api()            -> patched | stock
 *   info()           -> map            (enif_resource_cycles_info)
 *   graph()          -> map            (dry round: nodes, edges, why-alive)
 *   collect()        -> Round          (dirty: waits for a fresh round)
 *   subscribe(Pid|undefined) -> ok
 */
#include <dlfcn.h>
#include <string.h>
#include <erl_nif.h>
#include "erl_nif_trace.h"

typedef struct {
    ErlNifMutex *lock;
    ErlNifEnv *env;              /* owns the held term */
    ERL_NIF_TERM term;
    unsigned long long epoch;    /* bumped on every read and every write */
} Cell;

static ErlNifResourceType *CELL;
static volatile long LIVE;       /* cells not yet destroyed */

static struct {
    ErlNifSetResourceCycleHooksFn *set_hooks;
    ErlNifResourceCyclesTrackFn *track;
    ErlNifTraceEnvFn *trace_env;
    ErlNifResourceCyclesInfoFn *info;
    ErlNifResourceCyclesGraphFn *graph;
    ErlNifResourceCyclesCollectFn *collect;
    ErlNifResourceCyclesSubscribeFn *subscribe;
} API;

/* ---- hooks ---------------------------------------------------------------- */

static void cell_trace(ErlNifEnv *env, void *obj, ErlNifTraceCtx *ctx)
{
    Cell *c = obj;
    (void) env;
    enif_mutex_lock(c->lock);
    if (c->env)
        API.trace_env(ctx, c->env);
    enif_mutex_unlock(c->lock);
}

static void cell_clear(ErlNifEnv *env, void *obj)
{
    Cell *c = obj;
    ErlNifEnv *old;
    (void) env;
    enif_mutex_lock(c->lock);
    old = c->env;
    c->env = NULL;
    c->term = 0;
    __atomic_add_fetch(&c->epoch, 1, __ATOMIC_SEQ_CST);
    enif_mutex_unlock(c->lock);
    if (old)
        enif_free_env(old);      /* releases counts; outside our lock */
}

static unsigned long long cell_epoch(void *obj)
{
    return __atomic_load_n(&((Cell *) obj)->epoch, __ATOMIC_SEQ_CST);
}

static void cell_dtor(ErlNifEnv *env, void *obj)
{
    Cell *c = obj;
    (void) env;
    if (c->env)
        enif_free_env(c->env);
    enif_mutex_destroy(c->lock);
    __atomic_sub_fetch(&LIVE, 1, __ATOMIC_SEQ_CST);
}

/* ---- NIFs ----------------------------------------------------------------- */

static ERL_NIF_TERM nif_new(ErlNifEnv *env, int argc, const ERL_NIF_TERM argv[])
{
    Cell *c = enif_alloc_resource(CELL, sizeof(Cell));
    ERL_NIF_TERM r;
    (void) argc;
    c->lock = enif_mutex_create("rc_cell");
    c->env = enif_alloc_env();
    c->term = enif_make_copy(c->env, argv[0]);
    c->epoch = 0;
    __atomic_add_fetch(&LIVE, 1, __ATOMIC_SEQ_CST);
    if (API.track)
        API.track(c);            /* fully built: the collector may look */
    r = enif_make_resource(env, c);
    enif_release_resource(c);
    return r;
}

static ERL_NIF_TERM nif_put(ErlNifEnv *env, int argc, const ERL_NIF_TERM argv[])
{
    Cell *c;
    ErlNifEnv *fresh, *old;
    (void) argc;
    if (!enif_get_resource(env, argv[0], CELL, (void **) &c))
        return enif_make_badarg(env);
    fresh = enif_alloc_env();
    ERL_NIF_TERM t = enif_make_copy(fresh, argv[1]);
    enif_mutex_lock(c->lock);
    old = c->env;
    c->env = fresh;
    c->term = t;
    __atomic_add_fetch(&c->epoch, 1, __ATOMIC_SEQ_CST);
    enif_mutex_unlock(c->lock);
    if (old)
        enif_free_env(old);
    return enif_make_atom(env, "ok");
}

static ERL_NIF_TERM nif_get(ErlNifEnv *env, int argc, const ERL_NIF_TERM argv[])
{
    Cell *c;
    ERL_NIF_TERM out;
    (void) argc;
    if (!enif_get_resource(env, argv[0], CELL, (void **) &c))
        return enif_make_badarg(env);
    enif_mutex_lock(c->lock);
    /* The read is what the collector's validation must see: bump BEFORE the
     * copy, under the lock, so a racing round rejects this cell. */
    __atomic_add_fetch(&c->epoch, 1, __ATOMIC_SEQ_CST);
    out = c->env ? enif_make_copy(env, c->term) : enif_make_atom(env, "reclaimed");
    enif_mutex_unlock(c->lock);
    return out;
}

static ERL_NIF_TERM nif_live(ErlNifEnv *env, int argc, const ERL_NIF_TERM argv[])
{
    (void) argc; (void) argv;
    return enif_make_long(env, __atomic_load_n(&LIVE, __ATOMIC_SEQ_CST));
}

static ERL_NIF_TERM nif_api(ErlNifEnv *env, int argc, const ERL_NIF_TERM argv[])
{
    (void) argc; (void) argv;
    return enif_make_atom(env, API.track ? "patched" : "stock");
}

#define NEED_API(env) do { if (!API.track) return enif_make_atom(env, "stock"); } while (0)

static ERL_NIF_TERM nif_info(ErlNifEnv *env, int argc, const ERL_NIF_TERM argv[])
{
    (void) argc; (void) argv;
    NEED_API(env);
    return API.info(env);
}

static ERL_NIF_TERM nif_graph(ErlNifEnv *env, int argc, const ERL_NIF_TERM argv[])
{
    (void) argc; (void) argv;
    NEED_API(env);
    return API.graph(env);
}

static ERL_NIF_TERM nif_collect(ErlNifEnv *env, int argc, const ERL_NIF_TERM argv[])
{
    (void) argc; (void) argv;
    NEED_API(env);
    return enif_make_ulong(env, API.collect(env, 1));
}

static ERL_NIF_TERM nif_subscribe(ErlNifEnv *env, int argc, const ERL_NIF_TERM argv[])
{
    ErlNifPid pid;
    (void) argc;
    NEED_API(env);
    if (enif_get_local_pid(env, argv[0], &pid))
        API.subscribe(env, &pid);
    else
        API.subscribe(env, NULL);
    return enif_make_atom(env, "ok");
}

/* ---- load ----------------------------------------------------------------- */

static int load(ErlNifEnv *env, void **priv, ERL_NIF_TERM info)
{
    ErlNifResourceTypeInit init = {cell_dtor, NULL, NULL, 1, NULL};
    (void) priv; (void) info;
    CELL = enif_init_resource_type(env, "rc_cell", &init,
                                   ERL_NIF_RT_CREATE | ERL_NIF_RT_TAKEOVER, NULL);
    if (!CELL)
        return 1;
    /* Resolve the patched API from the emulator itself; absent on stock. */
    API.set_hooks = (ErlNifSetResourceCycleHooksFn *)
        dlsym(RTLD_DEFAULT, "enif_set_resource_cycle_hooks");
    if (API.set_hooks) {
        ErlNifResourceCycleHooks hooks = {cell_trace, cell_clear, cell_epoch};
        API.track = dlsym(RTLD_DEFAULT, "enif_resource_cycles_track");
        API.trace_env = dlsym(RTLD_DEFAULT, "enif_trace_env");
        API.info = dlsym(RTLD_DEFAULT, "enif_resource_cycles_info");
        API.graph = dlsym(RTLD_DEFAULT, "enif_resource_cycles_graph");
        API.collect = dlsym(RTLD_DEFAULT, "enif_resource_cycles_collect");
        API.subscribe = dlsym(RTLD_DEFAULT, "enif_resource_cycles_subscribe");
        if (API.set_hooks(CELL, &hooks) != 0)
            memset(&API, 0, sizeof(API));
    }
    return 0;
}

static ErlNifFunc funcs[] = {
    {"new", 1, nif_new, 0},
    {"put", 2, nif_put, 0},
    {"get", 1, nif_get, 0},
    {"live", 0, nif_live, 0},
    {"api", 0, nif_api, 0},
    {"info", 0, nif_info, 0},
    {"graph", 0, nif_graph, ERL_NIF_DIRTY_JOB_CPU_BOUND},
    {"collect", 0, nif_collect, ERL_NIF_DIRTY_JOB_CPU_BOUND},
    {"subscribe", 1, nif_subscribe, 0},
};

ERL_NIF_INIT(rc_cell, funcs, load, NULL, NULL, NULL)
