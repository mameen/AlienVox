//! Windows TTS backend — real SAPI 5 (`ISpVoice`) implementation.
//!
//! COM's `ISpVoice` lives in a single-threaded apartment and is **not** `Send`,
//! but Tauri commands run on arbitrary worker threads.  To bridge this we own the
//! voice on a dedicated STA thread and drive it through an `mpsc` channel.  The
//! public `NativeAudioEngine` only holds the `Sender`, which is `Send`.

use std::collections::HashSet;
use std::ffi::c_void;
use std::sync::mpsc::{channel, Sender};
use std::thread;

use windows::core::{w, HSTRING, PCWSTR, PWSTR};
use windows::Win32::Media::Speech::{
    IEnumSpObjectTokens, ISpObjectToken, ISpObjectTokenCategory, ISpVoice, SpObjectToken,
    SpObjectTokenCategory, SpVoice, SPCAT_VOICES, SPF_ASYNC, SPF_IS_XML, SPF_PURGEBEFORESPEAK,
};
use windows::Win32::System::Com::{
    CoCreateInstance, CoInitializeEx, CoTaskMemFree, CoUninitialize, CLSCTX_ALL,
    COINIT_APARTMENTTHREADED,
};

/// A single installed SAPI voice: its stable token id and friendly display name.
#[derive(Clone, Debug)]
pub struct VoiceEntry {
    pub id: String,
    pub name: String,
}

/// Commands sent to the dedicated SAPI thread.
enum Cmd {
    Speak {
        text: String,
        rate: i32,
        pitch: i32,
        volume: u8,
        voice_id: Option<String>,
    },
    Pause,
    Resume,
    Stop,
    ListVoices {
        engine: String,
        reply: Sender<Vec<VoiceEntry>>,
    },
}

#[allow(dead_code)]
pub struct NativeAudioEngine {
    tx: Sender<Cmd>,
}

#[allow(dead_code)]
impl NativeAudioEngine {
    /// Spawn the STA thread that owns the `ISpVoice` and process commands.
    pub fn new() -> Result<Self, String> {
        let (tx, rx) = channel::<Cmd>();

        thread::spawn(move || unsafe {
            // COM must be initialized on this thread before creating SpVoice.
            let _ = CoInitializeEx(None, COINIT_APARTMENTTHREADED);

            let voice: ISpVoice = match CoCreateInstance(&SpVoice, None, CLSCTX_ALL) {
                Ok(v) => v,
                Err(e) => {
                    eprintln!("[Windows TTS] Failed to create SpVoice: {e}");
                    CoUninitialize();
                    return;
                }
            };

            while let Ok(cmd) = rx.recv() {
                match cmd {
                    Cmd::Speak {
                        text,
                        rate,
                        pitch,
                        volume,
                        voice_id,
                    } => {
                        // Select a specific installed voice if one was requested;
                        // otherwise fall through to the current (default) voice.
                        if let Some(id) = voice_id.as_deref() {
                            match create_token_from_id(id) {
                                Ok(token) => {
                                    let _ = voice.SetVoice(&token);
                                }
                                Err(e) => eprintln!("[Windows TTS] SetVoice failed for {id}: {e}"),
                            }
                        }
                        // Rate: SAPI accepts -10..=10 directly.
                        let _ = voice.SetRate(rate.clamp(-10, 10));
                        // Volume: SAPI accepts 0..=100.
                        let _ = voice.SetVolume(volume.min(100) as u16);

                        // Pitch has no direct setter — apply it via inline SAPI XML.
                        let xml = format!(
                            "<pitch absmiddle=\"{}\"/>{}",
                            pitch.clamp(-10, 10),
                            escape_xml(&text)
                        );
                        let wide: Vec<u16> = xml.encode_utf16().chain(std::iter::once(0)).collect();
                        let flags = (SPF_ASYNC.0 | SPF_PURGEBEFORESPEAK.0 | SPF_IS_XML.0) as u32;
                        if let Err(e) = voice.Speak(PCWSTR(wide.as_ptr()), flags, None) {
                            eprintln!("[Windows TTS] Speak failed: {e}");
                        }
                    }
                    Cmd::Pause => {
                        let _ = voice.Pause();
                    }
                    Cmd::Resume => {
                        let _ = voice.Resume();
                    }
                    Cmd::Stop => {
                        // Purge the queue with an empty utterance to halt playback.
                        let flags = (SPF_ASYNC.0 | SPF_PURGEBEFORESPEAK.0) as u32;
                        let _ = voice.Speak(PCWSTR::null(), flags, None);
                    }
                    Cmd::ListVoices { engine, reply } => {
                        let voices = match enumerate_engine(&engine) {
                            Ok(v) => v,
                            Err(e) => {
                                eprintln!("[Windows TTS] Voice enumeration failed: {e}");
                                Vec::new()
                            }
                        };
                        let _ = reply.send(voices);
                    }
                }
            }

            CoUninitialize();
        });

        Ok(NativeAudioEngine { tx })
    }

    pub fn speak(
        &self,
        text: &str,
        rate: i32,
        pitch: i32,
        volume: u8,
        voice_id: Option<String>,
    ) -> Result<(), String> {
        self.tx
            .send(Cmd::Speak {
                text: text.to_string(),
                rate,
                pitch,
                volume,
                voice_id,
            })
            .map_err(|e| format!("TTS thread unavailable: {e}"))
    }

    /// Enumerate installed voices for `engine` via a synchronous round-trip to the
    /// STA thread.  `engine` selects which registry categories are scanned.
    pub fn list_voices(&self, engine: &str) -> Vec<VoiceEntry> {
        let (reply, rx) = channel();
        if self
            .tx
            .send(Cmd::ListVoices {
                engine: engine.to_string(),
                reply,
            })
            .is_err()
        {
            return Vec::new();
        }
        rx.recv().unwrap_or_default()
    }

    pub fn pause(&self) {
        let _ = self.tx.send(Cmd::Pause);
    }

    pub fn resume(&self) {
        let _ = self.tx.send(Cmd::Resume);
    }

    pub fn stop(&self) {
        let _ = self.tx.send(Cmd::Stop);
    }
}

/// Escape the characters that are significant inside SAPI XML markup.
fn escape_xml(input: &str) -> String {
    input
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

/// OneCore voice category.  Voices added through Windows Settings ("Add voices")
/// and several modern voices (e.g. Microsoft Mark) register here rather than under
/// the classic SAPI5 `SPCAT_VOICES` path, so both categories must be scanned.
const SPCAT_VOICES_ONECORE: PCWSTR =
    w!("HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech_OneCore\\Voices");

/// Microsoft Speech Platform (Speech Server v11) voice category.  Present only when
/// the Speech Platform runtime + language packs are installed; absent by default.
const SPCAT_VOICES_SPEECH_SERVER: PCWSTR =
    w!("HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech Server\\v11.0\\Voices");

/// Enumerate installed voices for the given engine tab, de-duplicating by display
/// name.  STA-thread only.
///
/// - `"sapi5"` — classic SAPI5 desktop voices plus modern OneCore voices.
/// - `"speech_platform"` — Microsoft Speech Platform (Speech Server v11) voices.
/// - anything else (e.g. `"sapi4"`, `"ml"`) — no SAPI-enumerable voices.
unsafe fn enumerate_engine(engine: &str) -> windows::core::Result<Vec<VoiceEntry>> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();

    match engine {
        "sapi5" => {
            // Classic SAPI5 desktop voices (always present).
            collect_from_category(SPCAT_VOICES, &mut out, &mut seen)?;
            // Modern OneCore voices — may be absent on older systems, so ignore errors.
            let _ = collect_from_category(SPCAT_VOICES_ONECORE, &mut out, &mut seen);
        }
        "speech_platform" => {
            // Speech Server category is absent unless the runtime is installed.
            let _ = collect_from_category(SPCAT_VOICES_SPEECH_SERVER, &mut out, &mut seen);
        }
        _ => {}
    }

    Ok(out)
}

/// Append every voice token in `category_id` to `out`, skipping names already seen.
unsafe fn collect_from_category(
    category_id: PCWSTR,
    out: &mut Vec<VoiceEntry>,
    seen: &mut HashSet<String>,
) -> windows::core::Result<()> {
    let category: ISpObjectTokenCategory =
        CoCreateInstance(&SpObjectTokenCategory, None, CLSCTX_ALL)?;
    category.SetId(category_id, false)?;

    let tokens: IEnumSpObjectTokens = category.EnumTokens(PCWSTR::null(), PCWSTR::null())?;
    let mut count = 0u32;
    tokens.GetCount(&mut count)?;

    for _ in 0..count {
        let mut token: Option<ISpObjectToken> = None;
        tokens.Next(1, &mut token, None)?;
        let token = match token {
            Some(t) => t,
            None => break,
        };

        let id = pwstr_to_string(token.GetId()?);
        // The token's default value holds the friendly name, e.g.
        // "Microsoft Zira Desktop - English (United States)".
        let name = match token.GetStringValue(PCWSTR::null()) {
            Ok(p) => pwstr_to_string(p),
            Err(_) => id.clone(),
        };

        if seen.insert(name.clone()) {
            out.push(VoiceEntry { id, name });
        }
    }
    Ok(())
}

/// Build an `ISpObjectToken` from a stable token id string.  STA-thread only.
unsafe fn create_token_from_id(id: &str) -> windows::core::Result<ISpObjectToken> {
    let token: ISpObjectToken = CoCreateInstance(&SpObjectToken, None, CLSCTX_ALL)?;
    token.SetId(PCWSTR::null(), &HSTRING::from(id), false)?;
    Ok(token)
}

/// Copy a SAPI-allocated `PWSTR` into an owned `String`, then free the buffer.
unsafe fn pwstr_to_string(p: PWSTR) -> String {
    if p.is_null() {
        return String::new();
    }
    let s = p.to_string().unwrap_or_default();
    CoTaskMemFree(Some(p.0 as *const c_void));
    s
}
