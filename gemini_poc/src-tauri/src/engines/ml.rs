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
#[serde(rename_all = "camelCase")]
pub struct MlModel {
    pub id: String,
    pub name: String,
    pub status: String,
    pub note: String,
}

struct WorkerProcess {
    child: Child,
    stdin: ChildStdin,
}

pub struct MlEngine {
    model_dirs: Vec<PathBuf>,
    worker: Arc<Mutex<Option<WorkerProcess>>>,
}

impl MlEngine {
    pub fn new(model_dirs: Vec<PathBuf>) -> Self {
        Self {
            model_dirs,
            worker: Arc::new(Mutex::new(None)),
        }
    }

    pub fn models(&self) -> Vec<MlModel> {
        vec![
            MlModel {
                id: KOKORO_MODEL_ID.to_string(),
                name: "Kokoro-82M".to_string(),
                status: "Ready".to_string(),
                note: "High quality local dev path; warm TTL defaults to 30s.".to_string(),
            },
            MlModel {
                id: PIPER_MODEL_ID.to_string(),
                name: "Piper".to_string(),
                status: if self.piper_model_path().is_some() {
                    "Ready"
                } else {
                    "Not installed"
                }
                .to_string(),
                note: "Fast offline fallback using en_US-lessac-medium.".to_string(),
            },
            MlModel {
                id: "vibevoice-realtime-0.5b".to_string(),
                name: "VibeVoice-Realtime-0.5B".to_string(),
                status: if self.snapshot_model_installed("vibevoice-realtime-0.5b") {
                    "Ready"
                } else {
                    "Not installed"
                }
                .to_string(),
                note: "MIT local streaming candidate from the SOTA doc; benchmark next."
                    .to_string(),
            },
            MlModel {
                id: "zonos2".to_string(),
                name: "ZONOS2".to_string(),
                status: if self.snapshot_model_installed("zonos2") {
                    "Ready"
                } else {
                    "Not installed"
                }
                .to_string(),
                note: "Apache 2.0 high-quality local candidate; likely GPU-oriented.".to_string(),
            },
            MlModel {
                id: "dia".to_string(),
                name: "Dia".to_string(),
                status: if self.snapshot_model_installed("dia") {
                    "Ready"
                } else {
                    "Not installed"
                }
                .to_string(),
                note: "Apache 2.0 expressive dialogue candidate; not first for selection reading."
                    .to_string(),
            },
        ]
    }

    pub fn list_model_voices(&self, model: &str) -> Result<Vec<Voice>> {
        match model {
            "" | KOKORO_MODEL_ID => self.list_voices(),
            PIPER_MODEL_ID => Ok(vec![Voice {
                id: "en_US-lessac-medium".to_string(),
                name: "Piper en_US lessac medium".to_string(),
            }]),
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
                self.speak_piper(text, params)
            }
            "vibevoice-realtime-0.5b" => {
                self.stop_kokoro_worker()?;
                Err(anyhow!(
                    "VibeVoice-Realtime-0.5B is listed but not installed yet."
                ))
            }
            "zonos2" => {
                self.stop_kokoro_worker()?;
                Err(anyhow!("ZONOS2 is listed but not installed yet."))
            }
            "dia" => {
                self.stop_kokoro_worker()?;
                Err(anyhow!("Dia is listed but not installed yet."))
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
            PIPER_MODEL_ID => self.export_piper_wav(text, params),
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

    fn model_dir(&self, name: &str) -> Option<PathBuf> {
        self.model_dirs
            .iter()
            .map(|dir| dir.join(name))
            .find(|dir| dir.exists())
    }

    fn snapshot_model_installed(&self, name: &str) -> bool {
        self.model_dir(name).is_some_and(|dir| {
            dir.join("alienvox-install.json").exists()
                || dir.join("config.json").exists()
                || dir.join("model_index.json").exists()
        })
    }

    fn run_piper(
        &self,
        text: &str,
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
        let model = self
            .piper_model_path()
            .ok_or_else(|| anyhow!("Piper voice is not installed under .models/ml/piper"))?;
        let config = self
            .piper_config_path()
            .ok_or_else(|| anyhow!("Piper config is not installed under .models/ml/piper"))?;
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
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .env("OMP_NUM_THREADS", "2")
            .env("MKL_NUM_THREADS", "2")
            .env("NUMEXPR_NUM_THREADS", "2");
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

    fn speak_piper(&self, text: &str, params: &SpeakParams) -> Result<()> {
        self.run_piper(text, params, None, false).map(|_| ())
    }

    fn export_piper_wav(&self, text: &str, params: &SpeakParams) -> Result<PathBuf> {
        let output = Self::export_path();
        self.run_piper(text, params, Some(&output), true)?;
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

impl TtsEngine for MlEngine {
    fn list_voices(&self) -> Result<Vec<Voice>> {
        Ok(vec![
            Voice {
                id: "af_heart".to_string(),
                name: "Kokoro af_heart".to_string(),
            },
            Voice {
                id: "af_bella".to_string(),
                name: "Kokoro af_bella".to_string(),
            },
            Voice {
                id: "af_nicole".to_string(),
                name: "Kokoro af_nicole".to_string(),
            },
            Voice {
                id: "af_sarah".to_string(),
                name: "Kokoro af_sarah".to_string(),
            },
            Voice {
                id: "af_sky".to_string(),
                name: "Kokoro af_sky".to_string(),
            },
            Voice {
                id: "am_adam".to_string(),
                name: "Kokoro am_adam".to_string(),
            },
            Voice {
                id: "am_michael".to_string(),
                name: "Kokoro am_michael".to_string(),
            },
            Voice {
                id: "bf_emma".to_string(),
                name: "Kokoro bf_emma".to_string(),
            },
            Voice {
                id: "bf_isabella".to_string(),
                name: "Kokoro bf_isabella".to_string(),
            },
            Voice {
                id: "bm_george".to_string(),
                name: "Kokoro bm_george".to_string(),
            },
            Voice {
                id: "bm_lewis".to_string(),
                name: "Kokoro bm_lewis".to_string(),
            },
        ])
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
