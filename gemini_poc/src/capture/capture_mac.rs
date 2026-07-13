use super::TextCapturer;

pub struct NativeCapturer;

impl NativeCapturer {
    pub fn new() -> Self {
        NativeCapturer
    }
}

impl TextCapturer for NativeCapturer {
    fn capture_selection(&self) -> Result<String, String> {
        Ok("Sample selected text from macOS".to_string())
    }
}
