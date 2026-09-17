PLAN-117 — the portless-name prototype, 2026-09-16

Throwaway programs, kept because the plan's design rests on what they showed. They are NOT product
code and must not be moved into `priv/`: I4 rebuilds the gateway from `gateway.bl` against the real
registry, the real CA and the real verbs.

## What each file is

| file | what it is |
|------|------------|
| `app.bl` | the app daemon: `(web/serve {:port 0 :ip {:local <derived path>} …})` — Bandit over a unix socket — plus the claim it writes (`:dest {:unix …}`, `:port 0`). Run with `bl serve`. |
| `claim.bl` | writes a claim for a FOREIGN server (a python `http.server` whose number the OS chose), from `CLAIM_NAME/HOST/PORT/PID/ROOT`. |
| `gateway.bl` | the prototype gateway: routes by `Host:` / absolute-form authority / CONNECT authority, mints a leaf per name from `BeamLisp.Daemon.CA`, splices to a unix path or a TCP port, serves `/bl.pac` + `/bl-ca.crt` + an index page, refuses a name no claim holds. |
| `portsview.bl` | prints the registry through the real `bl.ports/list-ports`, in the shape the plan proposes (name → destination → owner). |
| `up1.bl` | the TLS *upgrade* path alone: accept, `ssl.handshake(sock, opts, 15000)`, one reply. |
| `t3.bl` | the same, with the ownership hand-off: spawn a handler that waits for `[:go sock]`, `gen_tcp.controlling_process`, then handshake. Also proves bl's `receive` matches vector-tagged messages. |
| `t1.bl` | FFI semantics: map literals → atom-keyed Erlang maps, `erlang/apply` splicing, `String/to_integer`, `String.split`/`rest`/`some`/`join`. |
| `t5.bl` | the `[:safe]` probe: `Ports.list()` in a fresh VM vs one that has decoded a claim unsafely. |
| `verb2.bl` | seeds the atoms, then runs the real `bl.ports/run` over the prototype registry (the render evidence). |
| `app.log`, `gw.log` | the two daemons' startup lines, verbatim. |

## How it was run (scratch runtime dir — the user's registry is never touched)

    mkdir -p /tmp/bl117/run
    cd <checkout>
    XDG_RUNTIME_DIR=/tmp/bl117/run APP_HOST=web.knowledger.test ./bl serve !tasks/evidence/PLAN-117-prototype/app.bl
    XDG_RUNTIME_DIR=/tmp/bl117/run ./bl serve !tasks/evidence/PLAN-117-prototype/gateway.bl
    # a foreign server, on a number the OS chose:
    python3 -c 'import http.server,socketserver,os; os.chdir("/tmp/bl117/foreign-dir");\
      h=socketserver.TCPServer(("127.0.0.1",0),http.server.SimpleHTTPRequestHandler);\
      print(h.server_address[1],flush=True); h.serve_forever()'
    XDG_RUNTIME_DIR=/tmp/bl117/run CLAIM_NAME=api CLAIM_HOST=api.knowledger.test \
      CLAIM_PORT=<that number> CLAIM_PID=<its pid> CLAIM_ROOT=/tmp/bl117/foreign \
      ./bl run !tasks/evidence/PLAN-117-prototype/claim.bl

## What it showed (observed, not inferred)

- `bl serve` on a derived unix socket; Bandit logs `at …/3ee6b1d9fe7a49ed.web.sock (http+unix)`; the
  claim file records `:port 0` and `:dest {:unix …}`.
- `curl -x http://127.0.0.1:7788 http://web.knowledger.test/` and
  `curl -x http://127.0.0.1:7788 --cacert <ca>/root.pem https://web.knowledger.test/` both return the
  app's page. Nothing is bound to 80 or 443 (`ss -ltn` shows only the gateway's own port and the
  foreign server's number).
- An unknown name is refused over http AND at CONNECT (`curl: (7) CONNECT tunnel failed, response 404`),
  i.e. refused before any handshake — no claim, no leaf.
- Chrome (`--headless=new --proxy-pac-url=http://127.0.0.1:7788/bl.pac`): before the root is imported
  `net::ERR_CERT_AUTHORITY_INVALID`; after ONE user-level
  `certutil -A -n "beam-lisp local CA" -t "C,," -i <ca>/root.pem -d sql:$HOME/.pki/nssdb` the page
  renders — over both http and https, with no root anywhere.
- `ssl.handshake/3` on a socket accepted by `gen_tcp` succeeds ONLY when the caller owns it:
  `gen_tcp.controlling_process(sock, handler)` first, ordered by a message (`up1.bl` fails from a
  spawned handler, `t3.bl` passes). The induced failure is `{:error, {:dtls_upgrade, :notsup}}` — the
  same catch-all that masks a bad option list.
- `Ports.list()` returns `()` for a fresh VM and both claims for a VM that has decoded a claim without
  `[:safe]` (or whose source mentions `:dest`): `binary_to_term/2` with `[:safe]` refuses an unknown
  ATOM, so a new key silently empties the registry for readers that lack it.
- The real `bl.ports/run` render, over that registry:
  `web  http://web.knowledger.test/  → 0  app (pid 1641711)` — the `→ 0` row S2 replaces.

## What it does NOT show (so the plan does not claim it)

No TLS session-resumption test across two names; no load or concurrency measurement; no request
bodies/POST; no PAC through a system proxy (only Chrome's `--proxy-pac-url`); no allocator (the
gateway's port is a constant here); no route table (claims are read per request); and the CA wrote
under the runtime dir, not the state dir.
