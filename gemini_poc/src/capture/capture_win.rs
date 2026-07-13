pub struct NativeCapturer;

impl NativeCapturer {
    pub fn new() -> Self {
        NativeCapturer
    }

    pub fn capture_selection(&self) -> Result<String, String> {
        Ok("Sample selected text from Windows".to_string())
    }
}
