use super::AudioEngine;

pub struct NativeAudioEngine;

impl AudioEngine for NativeAudioEngine {
    fn speak(&self, text: &str) -> Result<(), String> {
        // Real implementation would invoke Win32 SAPI / ISpVoice
        println!("[Windows SAPI] Speaking: {}", text);
        Ok(())
    }
    
    fn stop(&self) {
        println!("[Windows SAPI] Stopped playback.");
    }
}
