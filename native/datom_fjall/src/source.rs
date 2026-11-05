//! Original generations are directory-claimed without engine open/recovery.
//! Actual read-only capabilities and store flocks, not caller flags, authorize
//! the physical capture. The accepted target publisher inherits this custody.
use super::{err, directory::{Directory, DirectoryHandle, OfflineScope}, sealing::{Custody, relative}};
use rustler::{NifResult, ResourceArc};
use std::path::PathBuf;
use std::sync::{Arc, atomic::Ordering};

pub(crate) struct Original {
    directory: Arc<Directory>, paths: Vec<String>,
    stores: Vec<Arc<Directory>>, _custody: Custody,
}
impl Original {
    fn check(&self) -> std::io::Result<()> {
        self.directory.check()?;
        for store in &self.stores { store.check()?; }
        Ok(())
    }
}
fn paths(mut paths: Vec<String>) -> std::io::Result<Vec<String>> {
    if paths.is_empty() || paths.len() > 256 { return Err(std::io::Error::other("invalid original store inventory")); }
    for path in &paths { relative(path)?; }
    // At most256 paths. Component-based tests avoid lexical prefix ambiguity.
    for (i, path) in paths.iter().enumerate() {
        for (j, other) in paths.iter().enumerate() {
            if i != j && PathBuf::from(path).starts_with(other) {
                return Err(std::io::Error::other("overlapping original stores"));
            }
        }
    }
    paths.sort(); Ok(paths)
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_offline_bind_source(scope: ResourceArc<OfflineScope>, source: ResourceArc<DirectoryHandle>, declared: Vec<String>) -> NifResult<bool> {
    let _job = scope.directory.root.write.lock().map_err(err)?;
    scope.directory.writable().map_err(err)?; scope.marker.check().map_err(err)?;
    source.0.check().map_err(err)?;
    if !source.0.readonly() || scope.directory.path.starts_with(&source.0.path) || source.0.path.starts_with(&scope.directory.path) {
        return Err(err("original must be a distinct read-only root"));
    }
    let _source = source.0.root.write.lock().map_err(err)?;
    source.0.check().map_err(err)?;
    if scope.directory.root.pins.load(Ordering::Acquire) != 0 { return Err(err("target already sealed")); }
    let mut binding = scope.source.lock().map_err(err)?;
    if binding.is_some() { return Err(err("original already bound")); }
    let declared = paths(declared).map_err(err)?;
    let mut stores = Vec::new();
    for path in &declared {
        let parts = relative(path).map_err(err)?; let mut current = source.0.clone();
        for (i, part) in parts.iter().enumerate() {
            current = current.child(part, false, i + 1 == parts.len()).map_err(err)?;
        }
        // Reading format markers is permitted; Config::open is never called.
        super::require_existing_engine(&current.path).map_err(err)?;
        stores.push(current);
    }
    source.0.check().map_err(err)?;
    source.0.root.pins.fetch_add(1, Ordering::AcqRel);
    *binding = Some(Arc::new(Original { directory: source.0.clone(), paths: declared, stores,
        _custody: Custody(source.0.root.clone()) }));
    Ok(true)
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_offline_check_source(scope: ResourceArc<OfflineScope>, source: ResourceArc<DirectoryHandle>, declared: Vec<String>) -> NifResult<bool> {
    let _job = scope.directory.root.write.lock().map_err(err)?;
    scope.directory.check().map_err(err)?; scope.marker.check().map_err(err)?;
    let binding = scope.source.lock().map_err(err)?;
    let bound = binding.as_ref().ok_or_else(|| err("no claimed original"))?;
    if !Arc::ptr_eq(&bound.directory, &source.0) || paths(declared).map_err(err)? != bound.paths {
        return Err(err("original claim or declared stores changed"));
    }
    bound.check().map_err(err)?;
    Ok(true)
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_offline_release_source(scope: ResourceArc<OfflineScope>) -> NifResult<bool> {
    let _job = scope.directory.root.write.lock().map_err(err)?;
    if scope.directory.root.pins.load(Ordering::Acquire) != 0 {
        return Err(err("sealed or accepted target still owns its original"));
    }
    scope.source.lock().map_err(err)?.take();
    Ok(true)
}
