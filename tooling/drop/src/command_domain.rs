//! Filesystem loans held by the OS service manager until the command's cgroup
//! empties. This transport conveys no Source invocation or writer authority.

pub fn dispatch(arguments: &[String]) -> Option<i32> {
    match arguments.first().map(String::as_str) {
        Some("--custody-protocol") => {
            println!("BEAM_LISP_CUSTODY_COMMAND_V1");
            Some(0)
        }
        Some("--custody-command") | Some("--custody-child") => {
            #[cfg(target_os = "linux")]
            let result = linux::dispatch(arguments);
            #[cfg(not(target_os = "linux"))]
            let result: Result<i32, String> = Err("managed command custody is unsupported on this target".into());
            Some(result.unwrap_or_else(|error| {
                eprintln!("bl: custody command refused: {error}");
                125
            }))
        }
        _ => None,
    }
}

#[cfg(target_os = "linux")]
mod linux {
    use std::fs::{File, OpenOptions};
    use std::io::{Read, Write};
    use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
    use std::os::linux::net::SocketAddrExt;
    use std::os::unix::net::{SocketAddr, UnixDatagram, UnixStream};
    use std::path::{Path, PathBuf};
    use std::process::{Command, Stdio};
    use std::time::{Duration, SystemTime, UNIX_EPOCH};
    use serde_json::Value;

    fn control(name: &str) -> Result<Command, String> {
        let uid = unsafe { libc::getuid() };
        if uid != unsafe { libc::geteuid() } { return Err("set-id command execution is unsupported".into()); }
        let path = ["/run/current-system/sw/bin", "/usr/bin", "/bin"].iter()
            .map(|directory| PathBuf::from(directory).join(name)).find(|path| path.is_file())
            .ok_or_else(|| format!("OS command controller {name} is unavailable"))?;
        let mut command = Command::new(path);
        // Request-local PATH/bus variables select the program's environment,
        // never the controller executable or its authenticated local manager.
        command.env_clear().env("XDG_RUNTIME_DIR", format!("/run/user/{uid}"))
            .env("DBUS_SESSION_BUS_ADDRESS", format!("unix:path=/run/user/{uid}/bus"))
            .env("PATH", "/run/current-system/sw/bin:/usr/bin:/bin");
        Ok(command)
    }

    fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str, String> {
        value.get(key).and_then(Value::as_str).ok_or_else(|| format!("missing string {key}"))
    }

    fn strings(value: &Value) -> Result<Vec<&str>, String> {
        value.as_array().ok_or("expected string array")?.iter()
            .map(|v| v.as_str().ok_or_else(|| "expected string array".to_string())).collect()
    }

    fn limit(value: &Value, key: &str, maximum: u64) -> Result<u64, String> {
        value.get("limits").and_then(|v| v.get(key)).and_then(Value::as_u64)
            .filter(|n| *n > 0 && *n <= maximum).ok_or_else(|| format!("invalid {key}"))
    }

    fn request(input: &str) -> Result<Value, String> {
        if input.len() > 65536 { return Err("request exceeds command capacity".into()); }
        let value: Value = serde_json::from_str(input).map_err(|e| e.to_string())?;
        if value.get("version").and_then(Value::as_u64) != Some(1) { return Err("unsupported protocol".into()); }
        let follower = strings(value.get("follower").ok_or("missing follower")?)?;
        if follower.len() != 3 || follower.iter().any(|s| s.is_empty()) { return Err("invalid follower context".into()); }
        for path in [follower[0], follower[1], text(&value, "program")?, text(&value, "cwd")?] {
            if !Path::new(path).is_absolute() || path.contains('\0') { return Err("absolute command addresses required".into()); }
        }
        strings(value.get("argv").ok_or("missing argv")?)?;
        let reads = strings(value.get("read_locks").ok_or("missing read locks")?)?;
        if reads.len() > 15 || reads.iter().any(|p| !Path::new(p).is_absolute()) { return Err("invalid read loans".into()); }
        limit(&value, "timeout_ms", 86_400_000)?;
        limit(&value, "memory_bytes", 8 * 1024 * 1024 * 1024)?;
        limit(&value, "output_bytes", 16 * 1024 * 1024)?;
        Ok(value)
    }

    pub fn dispatch(arguments: &[String]) -> Result<i32, String> {
        match (arguments.first().map(String::as_str), arguments.len()) {
            (Some("--custody-command"), 2) => launch(&arguments[1]),
            (Some("--custody-child"), 2) => child(&arguments[1]),
            _ => Err("invalid command protocol arguments".into()),
        }
    }

    fn launch(input: &str) -> Result<i32, String> {
        let mut value = request(input)?;
        // The caller's effective environment arrives through exec's private
        // environment, never as secret-bearing JSON on the command line.
        let mut environment = serde_json::Map::new();
        for (key, item) in std::env::vars_os() {
            environment.insert(key.into_string().map_err(|_| "non-UTF8 environment key")?,
                Value::String(item.into_string().map_err(|_| "non-UTF8 environment value")?));
        }
        value["env"] = Value::Object(environment);
        let bytes = serde_json::to_vec(&value).map_err(|e| e.to_string())?;
        if bytes.len() > 1024 * 1024 { return Err("command environment exceeds capacity".into()); }
        let raw = unsafe { libc::memfd_create(c"bl-command".as_ptr(), libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING) };
        if raw < 0 { return Err(std::io::Error::last_os_error().to_string()); }
        let mut credential = unsafe { File::from_raw_fd(raw) };
        credential.write_all(&bytes).map_err(|e| e.to_string())?;
        if unsafe { libc::fcntl(raw, libc::F_ADD_SEALS,
            libc::F_SEAL_SEAL | libc::F_SEAL_SHRINK | libc::F_SEAL_GROW | libc::F_SEAL_WRITE) } < 0 {
            return Err(std::io::Error::last_os_error().to_string());
        }
        let timeout = limit(&value, "timeout_ms", 86_400_000)?;
        let memory = limit(&value, "memory_bytes", 8 * 1024 * 1024 * 1024)?;
        let nonce = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos();
        let unit = format!("bl-custody-{}-{nonce}.service", std::process::id());
        let executable = std::env::current_exe().map_err(|e| e.to_string())?;
        let mut command = control("systemd-run")?;
        command.args(["--user", "--wait", "--pipe", "--collect", "--quiet"])
            .arg(format!("--unit={unit}"))
            .args(["--property=Type=notify", "--property=NotifyAccess=main", "--property=ExitType=cgroup",
                   "--property=FileDescriptorStoreMax=16", "--property=FileDescriptorStorePreserve=restart",
                   "--property=KillMode=control-group", "--property=TimeoutStartSec=10", "--property=TimeoutStopSec=2",
                   "--property=MemorySwapMax=0", "--property=TasksMax=512"])
            .arg(format!("--property=MemoryMax={memory}"))
            .arg(format!("--property=LoadCredential=bl-command:/proc/{}/fd/{raw}", std::process::id()))
            .arg(format!("--property=RuntimeMaxSec={}ms", timeout));
        // Preserve a caller's capped test slice for the whole managed tree.
        // Session scopes live outside the user manager; those use app.slice.
        if let Ok(group) = std::fs::read_to_string("/proc/self/cgroup") {
            if group.contains(".service/") {
                if let Some(slice) = group.trim().split('/').rev().find(|p| p.ends_with(".slice")) {
                    command.arg(format!("--slice={slice}"));
                }
            }
        }
        let (mut output, sink) = UnixStream::pair().map_err(|e| e.to_string())?;
        let sink_stdout: OwnedFd = sink.try_clone().map_err(|e| e.to_string())?.into();
        let sink_stderr: OwnedFd = sink.into();
        let mut process = command.arg(executable).args(["--custody-child", &unit])
            .stdin(Stdio::null()).stdout(Stdio::from(sink_stdout))
            .stderr(Stdio::from(sink_stderr)).spawn().map_err(|e| format!("cannot start OS command domain: {e}"))?;
        drop(command);
        let maximum = limit(&value, "output_bytes", 16 * 1024 * 1024)?;
        let mut count = 0u64;
        let mut buffer = [0u8; 8192];
        let mut forwarding = true;
        loop {
            let size = match output.read(&mut buffer) {
                Ok(0) => break,
                Ok(size) => size,
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(e) => return Err(e.to_string()),
            };
            count += size as u64;
            if count > maximum {
                let _ = control("systemctl")?.args(["--user", "stop", &unit]).status();
                let _ = process.wait();
                return Err("command output capacity exceeded; entire domain stopped".into());
            }
            if forwarding && std::io::stdout().write_all(&buffer[..size]).is_err() {
                // Caller disappearance is not proof of cancellation. Retain
                // accepted work and its loans; the OS deadline still applies.
                forwarding = false;
            }
        }
        let status = process.wait().map_err(|e| e.to_string())?;
        Ok(status.code().unwrap_or(125))
    }

    fn send_fds(socket: &UnixDatagram, bytes: &[u8], descriptors: &[i32]) -> Result<(), String> {
        // SCM_RIGHTS duplicates the actual open descriptions into the manager.
        // Aligned storage and checked CMSG sizes precede this single syscall.
        let length = std::mem::size_of_val(descriptors);
        let space = unsafe { libc::CMSG_SPACE(length as u32) as usize };
        let mut control = vec![0usize; space.div_ceil(std::mem::size_of::<usize>())];
        let mut io = libc::iovec { iov_base: bytes.as_ptr() as *mut _, iov_len: bytes.len() };
        let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
        message.msg_iov = &mut io;
        message.msg_iovlen = 1;
        message.msg_control = control.as_mut_ptr().cast();
        message.msg_controllen = space;
        unsafe {
            let header = libc::CMSG_FIRSTHDR(&message);
            if header.is_null() { return Err("invalid descriptor message capacity".into()); }
            (*header).cmsg_level = libc::SOL_SOCKET;
            (*header).cmsg_type = libc::SCM_RIGHTS;
            (*header).cmsg_len = libc::CMSG_LEN(length as u32) as usize;
            std::ptr::copy_nonoverlapping(descriptors.as_ptr().cast::<u8>(), libc::CMSG_DATA(header), length);
            if libc::sendmsg(socket.as_raw_fd(), &message, libc::MSG_NOSIGNAL) != bytes.len() as isize {
                return Err(std::io::Error::last_os_error().to_string());
            }
        }
        Ok(())
    }

    fn child(unit: &str) -> Result<i32, String> {
        let property = |name: &str| -> Result<String, String> {
            let reply = control("systemctl")?.args(["--user", "show", "--value", &format!("--property={name}"), unit])
                .output().map_err(|e| e.to_string())?;
            if !reply.status.success() { return Err("OS command domain unavailable".into()); }
            Ok(String::from_utf8_lossy(&reply.stdout).trim().into())
        };
        if property("MainPID")? != std::process::id().to_string()
            || property("NotifyAccess")? != "main" || property("ExitType")? != "cgroup"
            || property("FileDescriptorStorePreserve")? != "restart" {
            return Err("command helper is not the configured OS domain's main process".into());
        }
        let directory = std::env::var_os("CREDENTIALS_DIRECTORY").ok_or("missing private command credential")?;
        let input = std::fs::read_to_string(Path::new(&directory).join("bl-command")).map_err(|e| e.to_string())?;
        // The sealed private environment can be larger than the public header.
        let mut header: Value = serde_json::from_str(&input).map_err(|e| e.to_string())?;
        let environment = header.as_object_mut().ok_or("invalid command")?.remove("env").ok_or("missing environment")?;
        let value = request(&serde_json::to_string(&header).map_err(|e| e.to_string())?)?;
        let context = strings(&value["follower"])?;
        let lease = OpenOptions::new().read(true).write(true).open(context[0]).map_err(|e| e.to_string())?;
        lease.try_lock_shared().map_err(|e| format!("workspace custody changed: {e}"))?;
        if std::fs::read(context[1]).map_err(|e| e.to_string())? != context[2].as_bytes() {
            return Err("stale workspace cohort".into());
        }
        let mut loans: Vec<File> = vec![lease];
        for path in strings(&value["read_locks"])? {
            let loan = OpenOptions::new().read(true).write(true).open(path).map_err(|e| e.to_string())?;
            loan.try_lock_shared().map_err(|e| format!("read custody changed: {e}"))?;
            loans.push(loan);
        }
        let endpoint = std::env::var("NOTIFY_SOCKET").map_err(|_| "OS command domain notification unavailable")?;
        let address = if let Some(name) = endpoint.strip_prefix('@') {
            SocketAddr::from_abstract_name(name.as_bytes())
        } else { SocketAddr::from_pathname(endpoint) }.map_err(|e| e.to_string())?;
        let socket = UnixDatagram::unbound().map_err(|e| e.to_string())?;
        socket.connect_addr(&address).map_err(|e| e.to_string())?;
        let fds: Vec<_> = loans.iter().map(AsRawFd::as_raw_fd).collect();
        send_fds(&socket, b"FDSTORE=1\nFDNAME=bl_custody\nFDPOLL=0", &fds)?;
        let (mut barrier, receiver) = UnixStream::pair().map_err(|e| e.to_string())?;
        barrier.set_read_timeout(Some(Duration::from_secs(3))).map_err(|e| e.to_string())?;
        send_fds(&socket, b"BARRIER=1", &[receiver.as_raw_fd()])?;
        drop(receiver);
        let mut byte = [0];
        if barrier.read(&mut byte).map_err(|e| e.to_string())? != 0 { return Err("invalid loan acknowledgement".into()); }
        // Enqueue/processing acknowledgement alone does not prove storage.
        let observed = control("systemctl")?.args(["--user", "show", "--value", "--property=NFileDescriptorStore", unit])
            .output().map_err(|e| e.to_string())?;
        if !observed.status.success() || String::from_utf8_lossy(&observed.stdout).trim().parse::<usize>().ok() != Some(loans.len()) {
            return Err("OS manager did not retain every command loan".into());
        }
        drop(loans);
        socket.send(b"READY=1").map_err(|e| e.to_string())?;
        let mut command = Command::new(text(&value, "program")?);
        command.args(strings(&value["argv"])?).current_dir(text(&value, "cwd")?).env_clear().stdin(Stdio::null());
        for (key, item) in environment.as_object().ok_or("missing environment")? {
            // Notification and inherited-FD control belong to the manager.
            if !["NOTIFY_SOCKET", "FDSTORE", "LISTEN_PID", "LISTEN_FDS", "LISTEN_FDNAMES"].contains(&key.as_str()) {
                command.env(key, item.as_str().ok_or("invalid environment")?);
            }
        }
        let status = command.status().map_err(|e| format!("command could not start: {e}"))?;
        Ok(status.code().unwrap_or(125))
    }
}
