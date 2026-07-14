#[allow(dead_code)]
pub struct NativeAudioEngine;

#[allow(dead_code)]
impl NativeAudioEngine {
    #[allow(dead_code)]
    pub fn new() -> Self {
        NativeAudioEngine
    }

    #[allow(dead_code)]
    pub fn speak(&self, text: &str) -> Result<(), String> {
        println!("[Windows TTS] Speak: {}", text);
        Ok(())
    }

    #[allow(dead_code)]
    pub fn stop(&self) {
        println!("[Windows TTS] Stop playback.");
    }
}
