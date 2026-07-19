//! Layered YAML configuration (highlevel_design SKILL §5).
//!
//! Merge order (later wins):
//!   1. Built-in defaults (compiled)
//!   2. Stack config   — `.models/<stack>/stack.yaml` or `.apis/<provider>/provider.yaml`
//!   3. Model config   — `.models/<stack>/<model>/model.yaml`
//!   4. User overrides — `<app_local_data_dir>/user.yaml`
//!
//! Callers read the merged view via `resolve_effective`. User overrides are the
//! ONLY write sink (`save_user_overrides`) — every mutation round-trips through YAML.

#![allow(dead_code)]

use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_yaml::Value;
use tauri::AppHandle;

use crate::paths;

/// Merged, flattened view of the 4-layer config for a given (stack, model) pair.
#[derive(Debug, Clone, Serialize)]
pub struct EffectiveConfig {
    pub stack: String,
    pub model: Option<String>,
    /// Fully merged YAML tree — engine and UI both read from here.
    pub value: Value,
}

/// User-level overrides — the only writable layer. Holds the persisted UI state:
/// last-picked engine/model/voice + per-model control values.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct UserOverrides {
    /// Active engine tab (e.g. "ml", "sapi5").
    pub engine: Option<String>,
    /// Active model within the current stack (e.g. "kokoro", "piper").
    pub model: Option<String>,
    /// Per-stack overrides, keyed by stack id.
    #[serde(default)]
    pub stacks: BTreeMap<String, Value>,
    /// Per-model overrides, keyed by "<stack>/<model>".
    #[serde(default)]
    pub models: BTreeMap<String, Value>,
}

// ─── Path resolution ──────────────────────────────────────────────────────

/// `<first-existing model_dirs entry for stack>/stack.yaml`.
fn stack_config_path(app: &AppHandle, stack: &str) -> Option<PathBuf> {
    for dir in paths::model_dirs(app, stack) {
        let p = dir.join("stack.yaml");
        if p.exists() {
            return Some(p);
        }
    }
    // Also allow the writable location so the user can create one.
    paths::model_dirs(app, stack)
        .into_iter()
        .next()
        .map(|d| d.join("stack.yaml"))
}

fn model_config_path(app: &AppHandle, stack: &str, model: &str) -> Option<PathBuf> {
    for dir in paths::model_dirs(app, stack) {
        let p = dir.join(model).join("model.yaml");
        if p.exists() {
            return Some(p);
        }
    }
    paths::model_dirs(app, stack)
        .into_iter()
        .next()
        .map(|d| d.join(model).join("model.yaml"))
}

fn user_overrides_path(app: &AppHandle) -> Option<PathBuf> {
    paths::app_data_root(app).map(|d| d.join("user.yaml"))
}

// ─── YAML I/O ─────────────────────────────────────────────────────────────

fn read_yaml(path: &PathBuf) -> Result<Value> {
    if !path.exists() {
        return Ok(Value::Null);
    }
    let text = fs::read_to_string(path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    if text.trim().is_empty() {
        return Ok(Value::Null);
    }
    serde_yaml::from_str::<Value>(&text)
        .with_context(|| format!("invalid YAML in {}", path.display()))
}

fn write_yaml(path: &PathBuf, value: &Value) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    let text = serde_yaml::to_string(value)
        .with_context(|| format!("failed to serialize {}", path.display()))?;
    fs::write(path, text).with_context(|| format!("failed to write {}", path.display()))
}

// ─── Merge ────────────────────────────────────────────────────────────────

/// Deep-merge `overlay` into `base`. Maps merge key-by-key; scalars and sequences
/// are replaced wholesale by the overlay (list semantics are model-defined, so
/// we don't try to be clever).
fn merge(base: Value, overlay: Value) -> Value {
    match (base, overlay) {
        (Value::Mapping(mut b), Value::Mapping(o)) => {
            for (k, v) in o {
                let merged = match b.remove(&k) {
                    Some(existing) => merge(existing, v),
                    None => v,
                };
                b.insert(k, merged);
            }
            Value::Mapping(b)
        }
        // Overlay Null = "no override at this key" — keep base.
        (base, Value::Null) => base,
        (_, overlay) => overlay,
    }
}

// ─── Public API ───────────────────────────────────────────────────────────

/// Compile-time defaults injected as the base layer. Callers hand in the
/// engine's own built-in default `Value` so this module stays engine-agnostic.
pub fn resolve_effective(
    app: &AppHandle,
    stack: &str,
    model: Option<&str>,
    builtin_defaults: Value,
) -> Result<EffectiveConfig> {
    let mut merged = builtin_defaults;

    if let Some(p) = stack_config_path(app, stack) {
        merged = merge(merged, read_yaml(&p).unwrap_or(Value::Null));
    }
    if let Some(m) = model {
        if let Some(p) = model_config_path(app, stack, m) {
            merged = merge(merged, read_yaml(&p).unwrap_or(Value::Null));
        }
    }

    let user = load_user_overrides(app).unwrap_or_default();
    if let Some(v) = user.stacks.get(stack) {
        merged = merge(merged, v.clone());
    }
    if let Some(m) = model {
        let key = format!("{stack}/{m}");
        if let Some(v) = user.models.get(&key) {
            merged = merge(merged, v.clone());
        }
    }

    Ok(EffectiveConfig {
        stack: stack.to_string(),
        model: model.map(str::to_string),
        value: merged,
    })
}

pub fn load_user_overrides(app: &AppHandle) -> Result<UserOverrides> {
    let Some(path) = user_overrides_path(app) else {
        return Ok(UserOverrides::default());
    };
    if !path.exists() {
        return Ok(UserOverrides::default());
    }
    let text = fs::read_to_string(&path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    if text.trim().is_empty() {
        return Ok(UserOverrides::default());
    }
    serde_yaml::from_str(&text)
        .with_context(|| format!("invalid YAML in {}", path.display()))
}

pub fn save_user_overrides(app: &AppHandle, overrides: &UserOverrides) -> Result<()> {
    let path = user_overrides_path(app)
        .context("cannot resolve user.yaml path (app_local_data_dir unavailable)")?;
    let value = serde_yaml::to_value(overrides)
        .context("failed to serialize user overrides")?;
    write_yaml(&path, &value)
}

/// Apply a single per-model override patch and persist immediately.
/// Callers pass the field they changed (`{"speed": 1.2}`), it merges into
/// `models["<stack>/<model>"]`, and writes user.yaml.
pub fn set_model_override(
    app: &AppHandle,
    stack: &str,
    model: &str,
    patch: Value,
) -> Result<UserOverrides> {
    let mut overrides = load_user_overrides(app).unwrap_or_default();
    let key = format!("{stack}/{model}");
    let existing = overrides.models.remove(&key).unwrap_or(Value::Null);
    overrides.models.insert(key, merge(existing, patch));
    save_user_overrides(app, &overrides)?;
    Ok(overrides)
}

pub fn set_stack_override(
    app: &AppHandle,
    stack: &str,
    patch: Value,
) -> Result<UserOverrides> {
    let mut overrides = load_user_overrides(app).unwrap_or_default();
    let existing = overrides.stacks.remove(stack).unwrap_or(Value::Null);
    overrides.stacks.insert(stack.to_string(), merge(existing, patch));
    save_user_overrides(app, &overrides)?;
    Ok(overrides)
}

pub fn set_active_selection(
    app: &AppHandle,
    engine: Option<String>,
    model: Option<String>,
) -> Result<UserOverrides> {
    let mut overrides = load_user_overrides(app).unwrap_or_default();
    if engine.is_some() {
        overrides.engine = engine;
    }
    if model.is_some() {
        overrides.model = model;
    }
    save_user_overrides(app, &overrides)?;
    Ok(overrides)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_yaml::Value;

    fn yaml(s: &str) -> Value {
        serde_yaml::from_str(s).unwrap()
    }

    #[test]
    fn merge_replaces_scalar() {
        let base = yaml("speed: 1.0");
        let over = yaml("speed: 1.5");
        assert_eq!(merge(base, over), yaml("speed: 1.5"));
    }

    #[test]
    fn merge_deep_merges_maps() {
        let base = yaml("controls: {rate: {default: 0, min: -10}}");
        let over = yaml("controls: {rate: {default: 3}}");
        assert_eq!(
            merge(base, over),
            yaml("controls: {rate: {default: 3, min: -10}}")
        );
    }

    #[test]
    fn merge_replaces_sequence() {
        let base = yaml("voices: [a, b]");
        let over = yaml("voices: [c]");
        assert_eq!(merge(base, over), yaml("voices: [c]"));
    }
}
