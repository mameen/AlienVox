#[allow(dead_code)]
pub struct NativeCapturer;

#[allow(dead_code)]
impl NativeCapturer {
    #[allow(dead_code)]
    pub fn new() -> Self {
        NativeCapturer
    }

    #[allow(dead_code)]
    pub fn capture_selection(&self) -> Result<String, String> {
        Ok("Sample selected text from Windows".to_string())
    }
}
