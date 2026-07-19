//! Development ML/AI TTS backend.
//!
//! Kokoro is testable today through a warm local Python worker. Other SOTA
//! local/free candidates are exposed as model entries so the UI and preferences
//! can exercise model selection without pretending they are installed.

use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{anyhow, Context, Result};
use serde::Serialize;

use crate::telemetry;

use super::{SpeakParams, TtsEngine, Voice};

const KOKORO_MODEL_ID: &str = "kokoro";
const PIPER_MODEL_ID: &str = "piper";
pub const DEFAULT_MODEL_TTL_SECONDS: u64 = 30;
const MIN_MODEL_TTL_SECONDS: u64 = 0;
const MAX_MODEL_TTL_SECONDS: u64 = 300;

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MlModelState {
    /// Weights on disk AND a working runtime adapter exists — playable.
    Installed,
    /// No weights on disk (or Kokoro HF cache absent).
    NotInstalled,
    /// Weights on disk but no runtime adapter yet — install succeeded, playback not wired.
    Unavailable,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MlModel {
    pub id: String,
    pub name: String,
    pub status: String,
    pub state: MlModelState,
    pub note: String,
}

struct WorkerProcess {
    child: Child,
    stdin: ChildStdin,
}

pub struct MlEngine {
    model_dirs: Vec<PathBuf>,
    worker: Arc<Mutex<Option<WorkerProcess>>>,
    /// Held for one-way config resolution (SKILL §5). May be `None` in tests.
    app: Option<tauri::AppHandle>,
}

impl MlEngine {
    pub fn new(model_dirs: Vec<PathBuf>) -> Self {
        Self {
            model_dirs,
            worker: Arc::new(Mutex::new(None)),
            app: None,
        }
    }

    pub fn with_app(model_dirs: Vec<PathBuf>, app: tauri::AppHandle) -> Self {
        Self {
            model_dirs,
            worker: Arc::new(Mutex::new(None)),
            app: Some(app),
        }
    }

    /// Read the merged (defaults ← stack ← model ← user) config for a given model.
    fn effective(&self, model: &str) -> serde_yaml::Value {
        let Some(app) = &self.app else {
            return serde_yaml::Value::Null;
        };
        crate::config::resolve_effective(app, "ml", Some(model), serde_yaml::Value::Null)
            .map(|c| c.value)
            .unwrap_or(serde_yaml::Value::Null)
    }

    fn as_f64(v: &serde_yaml::Value, key: &str) -> Option<f64> {
        v.get(key).and_then(|x| x.as_f64())
    }
    fn as_i64(v: &serde_yaml::Value, key: &str) -> Option<i64> {
        v.get(key).and_then(|x| x.as_i64())
    }

    pub fn models(&self) -> Vec<MlModel> {
        let entry =
            |id: &str, name: &str, state: MlModelState, note: &str| -> MlModel {
                let status = match state {
                    MlModelState::Installed => "Ready",
                    MlModelState::NotInstalled => "Not installed",
                    MlModelState::Unavailable => "Installed (no runtime adapter)",
                };
                MlModel {
                    id: id.to_string(),
                    name: name.to_string(),
                    status: status.to_string(),
                    state,
                    note: note.to_string(),
                }
            };

        // Runnable adapters: kokoro (via warm worker), piper (via runner).
        // Weights-only models (vibevoice/zonos2/dia) have no runtime adapter yet — mark
        // Unavailable (yellow) when weights are present so the UI doesn't lie about playability.
        vec![
            entry(
                KOKORO_MODEL_ID,
                "Kokoro-82M",
                if self.kokoro_weights_installed() {
                    MlModelState::Installed
                } else {
                    MlModelState::NotInstalled
                },
                "High quality local dev path; warm TTL defaults to 30s.",
            ),
            entry(
                PIPER_MODEL_ID,
                "Piper",
                if self.piper_model_path().is_some() {
                    MlModelState::Installed
                } else {
                    MlModelState::NotInstalled
                },
                "Fast offline fallback using en_US-lessac-medium.",
            ),
            entry(
                "vibevoice-realtime-0.5b",
                "VibeVoice-Realtime-0.5B",
                if self.snapshot_weights_present("vibevoice-realtime-0.5b") {
                    MlModelState::Unavailable
                } else {
                    MlModelState::NotInstalled
                },
                "MIT local streaming candidate from the SOTA doc; benchmark next.",
            ),
            entry(
                "zonos2",
                "ZONOS2",
                if self.snapshot_weights_present("zonos2") {
                    MlModelState::Unavailable
                } else {
                    MlModelState::NotInstalled
                },
                "Apache 2.0 high-quality local candidate; likely GPU-oriented.",
            ),
            entry(
                "dia",
                "Dia",
                if self.snapshot_weights_present("dia") {
                    MlModelState::Unavailable
                } else {
                    MlModelState::NotInstalled
                },
                "Apache 2.0 expressive dialogue candidate; not first for selection reading.",
            ),
        ]
    }

    pub fn list_model_voices(&self, model: &str) -> Result<Vec<Voice>> {
        match model {
            "" | KOKORO_MODEL_ID => self.list_voices(),
            PIPER_MODEL_ID => Ok(self.piper_installed_voices()),
            "vibevoice-realtime-0.5b" => Ok(vec![Voice {
                id: "vibevoice-default".to_string(),
                name: "VibeVoice default (not installed)".to_string(),
            }]),
            "zonos2" => Ok(vec![Voice {
                id: "zonos2-default".to_string(),
                name: "ZONOS2 default (not installed)".to_string(),
            }]),
            "dia" => Ok(vec![Voice {
                id: "dia-default".to_string(),
                name: "Dia default (not installed)".to_string(),
            }]),
            other => Err(anyhow!("unknown ML model: {other}")),
        }
    }

    pub fn speak_with_model(
        &self,
        model: &str,
        text: &str,
        voice_id: &str,
        params: &SpeakParams,
    ) -> Result<()> {
        match model {
            "" | KOKORO_MODEL_ID => self.speak(text, voice_id, params),
            PIPER_MODEL_ID => {
                self.stop_kokoro_worker()?;
                self.speak_piper(text, voice_id, params)
            }
            "vibevoice-realtime-0.5b" | "zonos2" | "dia" => {
                self.stop_kokoro_worker()?;
                let present = self.snapshot_weights_present(model);
                Err(anyhow!(
                    "{model}: {}",
                    if present {
                        "weights installed, but the runtime adapter is not implemented yet"
                    } else {
                        "not installed — download it first from the model settings"
                    }
                ))
            }
            other => Err(anyhow!("unknown ML model: {other}")),
        }
    }

    pub fn export_wav(
        &self,
        model: &str,
        text: &str,
        voice_id: &str,
        params: &SpeakParams,
    ) -> Result<PathBuf> {
        match model {
            "" | KOKORO_MODEL_ID => self.export_kokoro_wav(text, voice_id, params),
            PIPER_MODEL_ID => self.export_piper_wav(text, voice_id, params),
            other => Err(anyhow!(
                "WAV export is not implemented for ML model: {other}"
            )),
        }
    }

    pub fn install_model_hint(&self, model: &str) -> Result<String> {
        self.start_model_install(model)
    }

    pub fn start_model_install(&self, model: &str) -> Result<String> {
        let (model, root, mut command) = self.install_command(model)?;
        let output = command
            .output()
            .with_context(|| format!("failed to launch installer for {model}"))?;
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        if !stdout.trim().is_empty() {
            eprintln!("[ML model installer stdout: {model}]\n{}", stdout.trim());
        }
        if !stderr.trim().is_empty() {
            eprintln!("[ML model installer stderr: {model}]\n{}", stderr.trim());
        }
        if !output.status.success() {
            return Err(anyhow!(
                "installer for {model} failed with {}",
                output.status
            ));
        }

        Ok(format!("Installed {model} under {}.", root.display()))
    }

    pub fn install_command(&self, model: &str) -> Result<(String, PathBuf, Command)> {
        let model = if model.trim().is_empty() {
            KOKORO_MODEL_ID
        } else {
            model
        };
        self.known_model(model)?;
        let installer = Self::model_installer();
        if !installer.exists() {
            return Err(anyhow!(
                "ML model installer not found at {}",
                installer.display()
            ));
        }

        let root = self.install_root()?;
        let hf_home = self.hf_home()?;
        let mut command = Command::new(Self::python_exe());
        command
            .arg(&installer)
            .arg("--model")
            .arg(model)
            .arg("--models-root")
            .arg(&root)
            .arg("--hf-home")
            .arg(&hf_home)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .env("HF_HOME", &hf_home)
            .env("OMP_NUM_THREADS", "2")
            .env("MKL_NUM_THREADS", "2")
            .env("NUMEXPR_NUM_THREADS", "2")
            .env("TORCH_NUM_THREADS", "2");

        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const BELOW_NORMAL_PRIORITY_CLASS: u32 = 0x0000_4000;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW);
        }

        Ok((model.to_string(), root, command))
    }

    fn known_model(&self, model: &str) -> Result<()> {
        match model {
            ""
            | KOKORO_MODEL_ID
            | PIPER_MODEL_ID
            | "vibevoice-realtime-0.5b"
            | "zonos2"
            | "dia" => Ok(()),
            other => Err(anyhow!("unknown ML model: {other}")),
        }
    }

    fn manifest_root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
    }

    fn dev_runner() -> PathBuf {
        Self::manifest_root().join("dev").join("kokoro_tts.py")
    }

    fn dev_worker() -> PathBuf {
        Self::manifest_root().join("dev").join("kokoro_worker.py")
    }

    fn piper_runner() -> PathBuf {
        Self::manifest_root().join("dev").join("piper_tts.py")
    }

    fn model_installer() -> PathBuf {
        Self::manifest_root()
            .join("dev")
            .join("install_ml_model.py")
    }

    fn python_exe() -> PathBuf {
        let poc_root = Self::manifest_root().join("..");
        let venv_python = if cfg!(windows) {
            poc_root.join(".venv").join("Scripts").join("python.exe")
        } else {
            poc_root.join(".venv").join("bin").join("python")
        };
        if venv_python.exists() {
            return venv_python;
        }
        PathBuf::from("python")
    }

    fn hf_home(&self) -> Result<PathBuf> {
        let root = self
            .model_dirs
            .iter()
            .find(|dir| dir.exists())
            .cloned()
            .or_else(|| self.model_dirs.first().cloned())
            .ok_or_else(|| anyhow!("no ML model directory candidates were resolved"))?;
        let cache = root.join("hf_home");
        std::fs::create_dir_all(&cache)
            .with_context(|| format!("failed to create {}", cache.display()))?;
        Ok(cache)
    }

    fn install_root(&self) -> Result<PathBuf> {
        let root = self
            .model_dirs
            .iter()
            .find(|dir| dir.exists())
            .cloned()
            .or_else(|| self.model_dirs.first().cloned())
            .ok_or_else(|| anyhow!("no ML model directory candidates were resolved"))?;
        std::fs::create_dir_all(&root)
            .with_context(|| format!("failed to create {}", root.display()))?;
        Ok(root)
    }

    fn normalized_ttl(seconds: u64) -> u64 {
        seconds.clamp(MIN_MODEL_TTL_SECONDS, MAX_MODEL_TTL_SECONDS)
    }

    fn ensure_kokoro_worker(&self, ttl_seconds: u64) -> Result<()> {
        let worker_path = Self::dev_worker();
        if !worker_path.exists() {
            return Err(anyhow!(
                "Kokoro worker not found at {}",
                worker_path.display()
            ));
        }

        let mut guard = self
            .worker
            .lock()
            .map_err(|_| anyhow!("ML engine lock poisoned"))?;
        if let Some(worker) = guard.as_mut() {
            if worker.child.try_wait()?.is_none() {
                return Ok(());
            }
        }
        *guard = None;

        let mut command = Command::new(Self::python_exe());
        command
            .arg(&worker_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .env("HF_HOME", self.hf_home()?)
            .env(
                "ALIENVOX_KOKORO_TTL_SECONDS",
                Self::normalized_ttl(ttl_seconds).to_string(),
            )
            .env("OMP_NUM_THREADS", "2")
            .env("MKL_NUM_THREADS", "2")
            .env("NUMEXPR_NUM_THREADS", "2")
            .env("TORCH_NUM_THREADS", "2");

        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const BELOW_NORMAL_PRIORITY_CLASS: u32 = 0x0000_4000;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW);
        }

        let mut child = command.spawn().context("failed to launch Kokoro worker")?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| anyhow!("Kokoro worker stdin unavailable"))?;
        let mut stderr = child.stderr.take();
        thread::spawn(move || {
            if let Some(pipe) = stderr.take() {
                for line in BufReader::new(pipe).lines().map_while(Result::ok) {
                    telemetry::record_worker_line(&line);
                    if !line.starts_with("ALIENVOX_TELEMETRY ") {
                        eprintln!("[Kokoro worker stderr] {line}");
                    }
                }
            }
        });

        *guard = Some(WorkerProcess { child, stdin });
        Ok(())
    }

    fn send_kokoro_request(&self, text: &str, voice_id: &str, params: &SpeakParams) -> Result<()> {
        self.ensure_kokoro_worker(params.hot_ttl_seconds)?;
        let request = serde_json::json!({
            "text": text,
            "voice": if voice_id.trim().is_empty() { "af_heart" } else { voice_id },
            "rate": params.rate,
            "pitch": params.pitch,
            "volume": params.volume,
            "hot_ttl_seconds": params.hot_ttl_seconds,
            "telemetry_request_id": params.telemetry_request_id,
            "requested_at_unix_ms": params.requested_at_unix_ms,
            "text_chars": params.text_chars,
            "text_bytes": params.text_bytes,
            "session_id": telemetry::session_id(),
        });

        let mut guard = self
            .worker
            .lock()
            .map_err(|_| anyhow!("ML engine lock poisoned"))?;
        let worker = guard
            .as_mut()
            .ok_or_else(|| anyhow!("Kokoro worker is not running"))?;
        writeln!(worker.stdin, "{request}")?;
        worker.stdin.flush()?;
        Ok(())
    }

    fn stop_kokoro_worker(&self) -> Result<()> {
        let mut guard = self
            .worker
            .lock()
            .map_err(|_| anyhow!("ML engine lock poisoned"))?;
        if let Some(worker) = guard.as_mut() {
            let _ = worker.child.kill();
            let _ = worker.child.wait();
        }
        *guard = None;
        Ok(())
    }

    fn text_file_path() -> PathBuf {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or_default();
        std::env::temp_dir().join(format!("alienvox-kokoro-{now}.txt"))
    }

    fn export_path() -> PathBuf {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or_default();
        std::env::current_dir()
            .unwrap_or_else(|_| Self::manifest_root())
            .join(format!("alienvox-export-{now}.wav"))
    }

    fn piper_dir(&self) -> Option<PathBuf> {
        self.model_dirs
            .iter()
            .map(|dir| dir.join("piper"))
            .find(|dir| dir.exists())
            .or_else(|| self.model_dirs.first().map(|dir| dir.join("piper")))
    }

    fn piper_model_path(&self) -> Option<PathBuf> {
        self.piper_dir()
            .map(|dir| dir.join("en_US-lessac-medium.onnx"))
            .filter(|path| path.exists())
    }

    fn piper_config_path(&self) -> Option<PathBuf> {
        self.piper_dir()
            .map(|dir| dir.join("en_US-lessac-medium.onnx.json"))
            .filter(|path| path.exists())
    }

    /// Enumerate every `*.onnx` under the Piper models dir.  Users can drop extra
    /// voices in (paired with `<voice>.onnx.json`) and they appear automatically.
    fn piper_installed_voices(&self) -> Vec<Voice> {
        let Some(dir) = self.piper_dir() else {
            return Vec::new();
        };
        let Ok(entries) = std::fs::read_dir(&dir) else {
            return Vec::new();
        };
        let mut voices: Vec<Voice> = entries
            .flatten()
            .filter_map(|e| {
                let path = e.path();
                let name = path.file_name()?.to_str()?.to_string();
                let stem = name.strip_suffix(".onnx")?.to_string();
                if !dir.join(format!("{stem}.onnx.json")).exists() {
                    return None;
                }
                let label = stem.replace('-', " · ").replace('_', " ");
                Some(Voice { id: stem, name: label })
            })
            .collect();
        voices.sort_by(|a, b| a.id.cmp(&b.id));
        voices
    }

    fn piper_voice_paths(&self, voice_id: &str) -> Option<(PathBuf, PathBuf)> {
        let dir = self.piper_dir()?;
        let onnx = dir.join(format!("{voice_id}.onnx"));
        let cfg = dir.join(format!("{voice_id}.onnx.json"));
        if onnx.exists() && cfg.exists() {
            Some((onnx, cfg))
        } else {
            None
        }
    }

    fn model_dir(&self, name: &str) -> Option<PathBuf> {
        self.model_dirs
            .iter()
            .map(|dir| dir.join(name))
            .find(|dir| dir.exists())
    }

    /// True iff the snapshot dir contains real model weights (not just metadata like
    /// `config.json`, which HF downloads early and leaves behind on failed pulls).
    /// Checks for common weight formats and honours the installer's success manifest.
    fn snapshot_weights_present(&self, name: &str) -> bool {
        let Some(dir) = self.model_dir(name) else {
            return false;
        };
        // Installer wrote a success manifest — trust it.
        if dir.join("alienvox-install.json").exists() {
            return true;
        }
        // Otherwise require an actual weight file.
        let Ok(read) = std::fs::read_dir(&dir) else {
            return false;
        };
        for entry in read.flatten() {
            let path = entry.path();
            let Some(name) = path.file_name().and_then(|s| s.to_str()) else {
                continue;
            };
            let lower = name.to_ascii_lowercase();
            if lower.ends_with(".safetensors")
                || lower.ends_with(".onnx")
                || lower.ends_with(".gguf")
                || lower == "pytorch_model.bin"
                || lower.starts_with("pytorch_model-")
            {
                return true;
            }
        }
        false
    }

    /// Kokoro runs from the HF cache under `<models_root>/hf_home/hub/*Kokoro*`.
    /// Treat any populated Kokoro snapshot dir as installed.
    fn kokoro_weights_installed(&self) -> bool {
        for root in &self.model_dirs {
            let hub = root.join("hf_home").join("hub");
            let Ok(entries) = std::fs::read_dir(&hub) else {
                continue;
            };
            for entry in entries.flatten() {
                let name = entry.file_name();
                let Some(name) = name.to_str() else { continue };
                if name.to_ascii_lowercase().contains("kokoro") {
                    let snapshots = entry.path().join("snapshots");
                    if snapshots.exists() {
                        if let Ok(mut inner) = std::fs::read_dir(&snapshots) {
                            if inner.next().is_some() {
                                return true;
                            }
                        }
                    }
                }
            }
        }
        false
    }

    fn run_piper(
        &self,
        text: &str,
        voice_id: &str,
        params: &SpeakParams,
        output: Option<&PathBuf>,
        wait: bool,
    ) -> Result<Option<PathBuf>> {
        if text.trim().is_empty() {
            return Ok(None);
        }
        let runner = Self::piper_runner();
        if !runner.exists() {
            return Err(anyhow!("Piper runner not found at {}", runner.display()));
        }
        let voice = if voice_id.trim().is_empty() {
            "en_US-lessac-medium"
        } else {
            voice_id
        };
        let (model, config) = self.piper_voice_paths(voice).ok_or_else(|| {
            anyhow!("Piper voice '{voice}' not installed under .models/ml/piper")
        })?;

        // Resolve piper-specific knobs from merged YAML (SKILL §5).
        let cfg = self.effective(PIPER_MODEL_ID);
        let noise_scale = Self::as_f64(&cfg, "noise_scale").unwrap_or(0.667);
        let noise_w = Self::as_f64(&cfg, "noise_w").unwrap_or(0.8);
        let sentence_silence = Self::as_f64(&cfg, "sentence_silence").unwrap_or(0.2);
        let length_scale = Self::as_f64(&cfg, "length_scale");
        let speaker = Self::as_i64(&cfg, "speaker").unwrap_or(-1);
        let text_file = Self::text_file_path();
        std::fs::write(&text_file, text)
            .with_context(|| format!("failed to write {}", text_file.display()))?;

        let mut command = Command::new(Self::python_exe());
        command
            .arg(&runner)
            .arg("--text-file")
            .arg(&text_file)
            .arg("--model")
            .arg(&model)
            .arg("--config")
            .arg(&config)
            .arg("--rate")
            .arg(params.rate.to_string())
            .arg("--volume")
            .arg(params.volume.to_string())
            .arg("--voice")
            .arg(voice)
            .arg("--noise-scale")
            .arg(noise_scale.to_string())
            .arg("--noise-w")
            .arg(noise_w.to_string())
            .arg("--sentence-silence")
            .arg(sentence_silence.to_string())
            .arg("--speaker")
            .arg(speaker.to_string())
            .arg("--hot-ttl-seconds")
            .arg(params.hot_ttl_seconds.to_string())
            .arg("--telemetry-request-id")
            .arg(&params.telemetry_request_id)
            .arg("--requested-at-unix-ms")
            .arg(params.requested_at_unix_ms.to_string())
            .arg("--text-chars")
            .arg(params.text_chars.to_string())
            .arg("--text-bytes")
            .arg(params.text_bytes.to_string())
            .arg("--session-id")
            .arg(telemetry::session_id())
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .env("OMP_NUM_THREADS", "2")
            .env("MKL_NUM_THREADS", "2")
            .env("NUMEXPR_NUM_THREADS", "2");
        if let Some(len) = length_scale {
            command.arg("--length-scale").arg(len.to_string());
        }
        if let Some(path) = output {
            command.arg("--output-wav").arg(path);
        }

        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const BELOW_NORMAL_PRIORITY_CLASS: u32 = 0x0000_4000;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW);
        }

        let mut child = command.spawn().context("failed to launch Piper runner")?;
        let mut stderr = child.stderr.take();
        if wait {
            let status = child.wait().context("failed to wait for Piper runner")?;
            let mut stderr_text = String::new();
            if let Some(mut pipe) = stderr.take() {
                let _ = pipe.read_to_string(&mut stderr_text);
            }
            if !stderr_text.trim().is_empty() {
                for line in stderr_text.lines() {
                    telemetry::record_worker_line(line);
                    if !line.starts_with("ALIENVOX_TELEMETRY ") {
                        eprintln!("[Piper runner stderr] {line}");
                    }
                }
            }
            if !status.success() {
                return Err(anyhow!("Piper runner failed with {status}"));
            }
            return Ok(output.cloned());
        }

        thread::spawn(move || {
            let mut stderr_text = String::new();
            if let Some(mut pipe) = stderr.take() {
                let _ = pipe.read_to_string(&mut stderr_text);
            }
            if !stderr_text.trim().is_empty() {
                for line in stderr_text.lines() {
                    telemetry::record_worker_line(line);
                    if !line.starts_with("ALIENVOX_TELEMETRY ") {
                        eprintln!("[Piper runner stderr] {line}");
                    }
                }
            }
            let _ = child.wait();
        });
        Ok(output.cloned())
    }

    fn speak_piper(&self, text: &str, voice_id: &str, params: &SpeakParams) -> Result<()> {
        self.run_piper(text, voice_id, params, None, false).map(|_| ())
    }

    fn export_piper_wav(&self, text: &str, voice_id: &str, params: &SpeakParams) -> Result<PathBuf> {
        let output = Self::export_path();
        self.run_piper(text, voice_id, params, Some(&output), true)?;
        Ok(output)
    }

    fn export_kokoro_wav(
        &self,
        text: &str,
        voice_id: &str,
        params: &SpeakParams,
    ) -> Result<PathBuf> {
        if text.trim().is_empty() {
            return Err(anyhow!("No text to export."));
        }

        let runner = Self::dev_runner();
        if !runner.exists() {
            return Err(anyhow!("ML/AI runner not found at {}", runner.display()));
        }

        let text_file = Self::text_file_path();
        std::fs::write(&text_file, text)
            .with_context(|| format!("failed to write {}", text_file.display()))?;
        let output = Self::export_path();

        let status = Command::new(Self::python_exe())
            .arg(&runner)
            .arg("--text-file")
            .arg(&text_file)
            .arg("--voice")
            .arg(if voice_id.trim().is_empty() {
                "af_heart"
            } else {
                voice_id
            })
            .arg("--rate")
            .arg(params.rate.to_string())
            .arg("--pitch")
            .arg(params.pitch.to_string())
            .arg("--volume")
            .arg(params.volume.to_string())
            .arg("--output-wav")
            .arg(&output)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::inherit())
            .env("HF_HOME", self.hf_home()?)
            .status()
            .context("failed to launch Kokoro WAV exporter")?;

        if !status.success() {
            return Err(anyhow!("Kokoro WAV export failed with {status}"));
        }
        Ok(output)
    }
}

/// Full Kokoro-82M voice roster (hexgrad/Kokoro-82M model card, 2026).
/// Format: (id, human label).  Prefix encodes locale + gender:
///   af/am = American F/M, bf/bm = British F/M, ef/em = Spanish, ff = French,
///   hf/hm = Hindi, if/im = Italian, jf/jm = Japanese, pf/pm = Brazilian PT,
///   zf/zm = Mandarin.
const KOKORO_VOICES: &[(&str, &str)] = &[
    // American English — Female
    ("af_heart", "American F · Heart"),
    ("af_alloy", "American F · Alloy"),
    ("af_aoede", "American F · Aoede"),
    ("af_bella", "American F · Bella"),
    ("af_jessica", "American F · Jessica"),
    ("af_kore", "American F · Kore"),
    ("af_nicole", "American F · Nicole"),
    ("af_nova", "American F · Nova"),
    ("af_river", "American F · River"),
    ("af_sarah", "American F · Sarah"),
    ("af_sky", "American F · Sky"),
    // American English — Male
    ("am_adam", "American M · Adam"),
    ("am_echo", "American M · Echo"),
    ("am_eric", "American M · Eric"),
    ("am_fenrir", "American M · Fenrir"),
    ("am_liam", "American M · Liam"),
    ("am_michael", "American M · Michael"),
    ("am_onyx", "American M · Onyx"),
    ("am_puck", "American M · Puck"),
    ("am_santa", "American M · Santa"),
    // British English
    ("bf_alice", "British F · Alice"),
    ("bf_emma", "British F · Emma"),
    ("bf_isabella", "British F · Isabella"),
    ("bf_lily", "British F · Lily"),
    ("bm_daniel", "British M · Daniel"),
    ("bm_fable", "British M · Fable"),
    ("bm_george", "British M · George"),
    ("bm_lewis", "British M · Lewis"),
    // Other locales
    ("ef_dora", "Spanish F · Dora"),
    ("em_alex", "Spanish M · Alex"),
    ("em_santa", "Spanish M · Santa"),
    ("ff_siwis", "French F · Siwis"),
    ("hf_alpha", "Hindi F · Alpha"),
    ("hf_beta", "Hindi F · Beta"),
    ("hm_omega", "Hindi M · Omega"),
    ("hm_psi", "Hindi M · Psi"),
    ("if_sara", "Italian F · Sara"),
    ("im_nicola", "Italian M · Nicola"),
    ("jf_alpha", "Japanese F · Alpha"),
    ("jf_gongitsune", "Japanese F · Gongitsune"),
    ("jf_nezumi", "Japanese F · Nezumi"),
    ("jf_tebukuro", "Japanese F · Tebukuro"),
    ("jm_kumo", "Japanese M · Kumo"),
    ("pf_dora", "Portuguese F · Dora"),
    ("pm_alex", "Portuguese M · Alex"),
    ("pm_santa", "Portuguese M · Santa"),
    ("zf_xiaobei", "Mandarin F · Xiaobei"),
    ("zf_xiaoni", "Mandarin F · Xiaoni"),
    ("zf_xiaoxiao", "Mandarin F · Xiaoxiao"),
    ("zf_xiaoyi", "Mandarin F · Xiaoyi"),
    ("zm_yunjian", "Mandarin M · Yunjian"),
    ("zm_yunxi", "Mandarin M · Yunxi"),
    ("zm_yunxia", "Mandarin M · Yunxia"),
    ("zm_yunyang", "Mandarin M · Yunyang"),
];

impl TtsEngine for MlEngine {
    fn list_voices(&self) -> Result<Vec<Voice>> {
        Ok(KOKORO_VOICES
            .iter()
            .map(|(id, name)| Voice {
                id: (*id).to_string(),
                name: (*name).to_string(),
            })
            .collect())
    }

    fn speak(&self, text: &str, voice_id: &str, params: &SpeakParams) -> Result<()> {
        if text.trim().is_empty() {
            return Ok(());
        }
        self.send_kokoro_request(text, voice_id, params)
    }

    fn pause(&self) -> Result<()> {
        Ok(())
    }

    fn resume(&self) -> Result<()> {
        Ok(())
    }

    fn stop(&self) -> Result<()> {
        self.stop_kokoro_worker()
    }
}
