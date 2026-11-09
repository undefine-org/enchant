#[path = "../formal/mod.rs"]
mod formal;

use std::io::{self, Read, Write};
use std::sync::mpsc;
use formal::wire::{Fault, MAX_PACKET};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut backend = None;
    let mut z3_library = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        match argument.as_str() {
            "--backend" => backend = args.next(),
            "--z3-library" => z3_library = args.next(),
            _ => return Err(format!("unknown formal-worker argument {argument}").into()),
        }
    }
    let mut session = formal::Session::new(backend.as_deref().unwrap_or("oxiz"), z3_library.as_deref())?;
    let (tx, rx) = mpsc::sync_channel(1);
    std::thread::spawn(move || {
        let mut input = io::stdin().lock();
        loop {
            let mut header = [0; 4];
            // EOF is the owning process's hard cancellation signal. It ends
            // a native search even when its own cooperative timeout stalls.
            if input.read_exact(&mut header).is_err() { std::process::exit(0); }
            let size = u32::from_be_bytes(header) as usize;
            if size == 0 || size > MAX_PACKET { std::process::exit(65); }
            let mut bytes = vec![0; size];
            if input.read_exact(&mut bytes).is_err() || tx.send(bytes).is_err() {
                std::process::exit(0);
            }
        }
    });
    let mut output = io::stdout().lock();
    for bytes in rx {
        let reply = if bytes.get(1) == Some(&80) {
            session.refuse(Fault::invalid("compressed ETF requests are not accepted"))
        } else {
            let mut cursor = io::Cursor::new(&bytes);
            match eetf::Term::decode(&mut cursor) {
                Ok(request) if cursor.position() == bytes.len() as u64 => session.handle(&request),
                Ok(_) => session.refuse(Fault::invalid("trailing bytes in ETF request")),
                Err(error) => session.refuse(Fault::invalid(format!("ETF decoding failed: {error}"))),
            }
        };
        let mut encoded = Vec::new();
        reply.encode(&mut encoded)?;
        if encoded.len() > MAX_PACKET { return Err("reply exceeds packet capacity".into()); }
        output.write_all(&(encoded.len() as u32).to_be_bytes())?;
        output.write_all(&encoded)?;
        output.flush()?;
    }
    Ok(())
}
