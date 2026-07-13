pub struct NativeAudioEngine;

impl NativeAudioEngine {
    pub fn new() -> Self {
        NativeAudioEngine
    }

    pub fn speak(&self, text: &str) -> Result<(), String> {
        println!("[Windows TTS] Speak: {}", text);
        Ok(())
    }

    pub fn stop(&self) {
        println!("[Windows TTS] Stop playback.");
    }
}
