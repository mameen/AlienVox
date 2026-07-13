use super::AudioEngine;

pub struct NativeAudioEngine;

impl NativeAudioEngine {
    pub fn new() -> Self {
        NativeAudioEngine
    }
}

impl AudioEngine for NativeAudioEngine {
    fn speak(&self, text: &str) -> Result<(), String> {
        println!("[macOS TTS] Speak: {}", text);
        Ok(())
    }

    fn stop(&self) {
        println!("[macOS TTS] Stop playback.");
    }
}
