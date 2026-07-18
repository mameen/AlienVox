//! Development ML/AI TTS backend.
//!
//! This is intentionally a local process bridge for the dev environment. It keeps
//! the Rust app free of neural-runtime dependencies while making the ML/AI tab
//! testable now. Deployment packaging is handled separately by ADR-003.

use std::path::PathBuf;
use std::io::Read;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{anyhow, Context, Result};

use super::{SpeakParams, TtsEngine, Voice};

pub struct MlEngine {
    model_dirs: Vec<PathBuf>,
    child: Arc<Mutex<Option<Child>>>,
}

impl MlEngine {
    pub fn new(model_dirs: Vec<PathBuf>) -> Self {
        Self {
            model_dirs,
            child: Arc::new(Mutex::new(None)),
        }
    }

    fn manifest_root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
    }

    fn dev_runner() -> PathBuf {
        Self::manifest_root().join("dev").join("kokoro_tts.py")
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

    fn text_file_path() -> PathBuf {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or_default();
        std::env::temp_dir().join(format!("alienvox-kokoro-{now}.txt"))
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
}

impl TtsEngine for MlEngine {
    fn list_voices(&self) -> Result<Vec<Voice>> {
        Ok(vec![
            Voice { id: "af_heart".to_string(), name: "Kokoro af_heart".to_string() },
            Voice { id: "af_bella".to_string(), name: "Kokoro af_bella".to_string() },
            Voice { id: "af_nicole".to_string(), name: "Kokoro af_nicole".to_string() },
            Voice { id: "af_sarah".to_string(), name: "Kokoro af_sarah".to_string() },
            Voice { id: "af_sky".to_string(), name: "Kokoro af_sky".to_string() },
            Voice { id: "am_adam".to_string(), name: "Kokoro am_adam".to_string() },
            Voice { id: "am_michael".to_string(), name: "Kokoro am_michael".to_string() },
            Voice { id: "bf_emma".to_string(), name: "Kokoro bf_emma".to_string() },
            Voice { id: "bf_isabella".to_string(), name: "Kokoro bf_isabella".to_string() },
            Voice { id: "bm_george".to_string(), name: "Kokoro bm_george".to_string() },
            Voice { id: "bm_lewis".to_string(), name: "Kokoro bm_lewis".to_string() },
        ])
    }

    fn speak(&self, text: &str, voice_id: &str, params: &SpeakParams) -> Result<()> {
        if text.trim().is_empty() {
            return Ok(());
        }

        self.stop()?;

        let runner = Self::dev_runner();
        if !runner.exists() {
            return Err(anyhow!(
                "ML/AI runner not found at {}",
                runner.display()
            ));
        }

        let text_file = Self::text_file_path();
        std::fs::write(&text_file, text)
            .with_context(|| format!("failed to write {}", text_file.display()))?;
        let hf_home = self.hf_home()?;

        let mut command = Command::new(Self::python_exe());
        command
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
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .env("HF_HOME", hf_home)
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

        let mut child = command
            .spawn()
            .context("failed to launch local ML/AI TTS runner")?;

        if let Some(status) = child.try_wait().context("failed to poll ML/AI runner")? {
            return Err(anyhow!("local ML/AI TTS runner exited immediately: {status}"));
        }

        let mut stderr = child.stderr.take();
        let child_slot = Arc::clone(&self.child);
        *child_slot.lock().map_err(|_| anyhow!("ML engine lock poisoned"))? = Some(child);

        thread::spawn(move || {
            let mut stderr_text = String::new();
            if let Some(mut pipe) = stderr.take() {
                let _ = pipe.read_to_string(&mut stderr_text);
            }

            let status = {
                let mut guard = match child_slot.lock() {
                    Ok(guard) => guard,
                    Err(_) => return,
                };
                let Some(mut child) = guard.take() else {
                    return;
                };
                child.wait().ok()
            };

            if !stderr_text.trim().is_empty() {
                eprintln!("[ML/AI TTS runner stderr]\n{}", stderr_text.trim());
            }
            if let Some(status) = status {
                if !status.success() {
                    eprintln!("[ML/AI TTS] Runner exited with {status}");
                }
            }
        });
        Ok(())
    }

    fn pause(&self) -> Result<()> {
        Ok(())
    }

    fn resume(&self) -> Result<()> {
        Ok(())
    }

    fn stop(&self) -> Result<()> {
        let mut guard = self.child.lock().map_err(|_| anyhow!("ML engine lock poisoned"))?;
        if let Some(child) = guard.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *guard = None;
        Ok(())
    }
}
