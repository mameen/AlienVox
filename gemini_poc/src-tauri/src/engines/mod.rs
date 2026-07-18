//! Multi-stack TTS engine abstraction (ADR-004).
//!
//! Every TTS stack — classic SAPI 5, the Microsoft Speech Platform, cross-platform
//! neural ML models, and (later) high-level library bridges — implements the single
//! [`TtsEngine`] trait, so commands and Preferences treat every stack identically.
//!
//! Engines use interior mutability (SAPI drives a dedicated STA thread through an
//! `mpsc` channel), so trait methods take `&self`.  The trait object must be `Send`;
//! the SAPI implementation holds only the `Sender` (which is `Send`), never the
//! `!Send` `ISpVoice`.  Errors use `anyhow::Result` internally and are converted to
//! `Result<_, String>` at the Tauri IPC boundary.
#![allow(dead_code)]

use anyhow::Result;

pub mod ml;

/// A selectable voice: stable `id` for selection, `name` for display.
///
/// Selection is always by the stable `id` (a SAPI token id, or a model file path),
/// because display names collide and are not stable.  Mirrors the frontend's
/// `VoiceInfo { id, name }` contract.
#[derive(Clone, Debug)]
pub struct Voice {
    pub id: String,
    pub name: String,
}

/// Prosody controlled by the UI.  A field is silently ignored by engines that lack
/// support for it (e.g. a neural voice with no pitch control).
#[derive(Clone, Copy, Debug)]
pub struct SpeakParams {
    pub rate: i32,
    pub pitch: i32,
    pub volume: u8,
}

/// The uniform interface every TTS stack implements.  Stored as
/// `Box<dyn TtsEngine + Send>` behind the active-stack selector.
pub trait TtsEngine {
    /// List the voices this stack can currently offer.
    fn list_voices(&self) -> Result<Vec<Voice>>;

    /// Speak `text` with the voice identified by `voice_id` (empty = default) and
    /// the given prosody.  Playback is asynchronous.
    fn speak(&self, text: &str, voice_id: &str, params: &SpeakParams) -> Result<()>;

    /// Pause ongoing playback.
    fn pause(&self) -> Result<()>;

    /// Resume previously paused playback.
    fn resume(&self) -> Result<()>;

    /// Immediately halt playback and purge any queued speech.
    fn stop(&self) -> Result<()>;
}

/// The selected TTS stack.  Variants match the frontend tab `data-engine` keys, so
/// the same string flows UI → command → Preferences persistence unchanged.
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActiveStack {
    /// Classic SAPI 5 (plus OneCore) — Windows only.
    Sapi5,
    /// Microsoft Speech Platform (Speech Server v11) — Windows only.
    SpeechPlatform,
    /// Cross-platform neural models (ort + rodio + espeak).
    Ml,
    /// Future high-level bridge (`tts` / `any-tts`).
    Library,
}

impl ActiveStack {
    /// The stacks selectable on the current target OS.  Stack availability is
    /// platform-dependent — the SAPI variants do not exist off Windows — so the
    /// registry filters per target via `cfg` (ADR-004 §4).  `sapi4` is intentionally
    /// absent: it is a disabled placeholder (dead API, not enumerable).
    pub fn available() -> Vec<ActiveStack> {
        let mut stacks = Vec::new();
        #[cfg(target_os = "windows")]
        {
            stacks.push(ActiveStack::Sapi5);
            stacks.push(ActiveStack::SpeechPlatform);
        }
        stacks.push(ActiveStack::Ml);
        stacks
    }
}
