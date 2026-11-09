//! One owned solver per OS process. stdout is exclusively packet-4 ETF.
mod engine;
mod wire;

use std::io::{self, Read, Write};
use std::sync::mpsc;
use wire::{MAX_PACKET, error};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let (tx, rx) = mpsc::sync_channel(1);
    std::thread::spawn(move || {
        let mut input = io::stdin().lock();
        loop {
            let mut header = [0; 4];
            // Closing the owning BEAM port closes stdin. This reader exits the
            // entire OS process even while the solver thread is busy: port
            // retirement therefore provides hard cancellation, not abandonment.
            if input.read_exact(&mut header).is_err() {
                std::process::exit(0);
            }
            let size = u32::from_be_bytes(header) as usize;
            if size == 0 || size > MAX_PACKET {
                std::process::exit(65);
            }
            let mut bytes = vec![0; size];
            if input.read_exact(&mut bytes).is_err() || tx.send(bytes).is_err() {
                std::process::exit(0);
            }
        }
    });
    let mut state = engine::Engine::new();
    let mut output = io::stdout().lock();
    for bytes in rx {
        let mut cursor = io::Cursor::new(&bytes);
        let result = eetf::Term::decode(&mut cursor)
            .map_err(|e| e.to_string())
            .and_then(|request| {
                if cursor.position() != bytes.len() as u64 {
                    return Err("trailing bytes in ETF request".into());
                }
                state.request(&request)
            });
        let reply = match result {
            Ok(reply) => reply,
            Err(message) => {
                // No failed partial script can contaminate the next request.
                state = engine::Engine::new();
                error(&message)
            }
        };
        let mut encoded = Vec::new();
        reply.encode(&mut encoded)?;
        if encoded.len() > MAX_PACKET {
            return Err("reply exceeds packet capacity".into());
        }
        output.write_all(&(encoded.len() as u32).to_be_bytes())?;
        output.write_all(&encoded)?;
        output.flush()?;
    }
    Ok(())
}
