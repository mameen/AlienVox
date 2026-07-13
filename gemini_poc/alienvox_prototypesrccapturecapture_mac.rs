use super::TextCapturer;

pub struct NativeCapturer;

impl TextCapturer for NativeCapturer {
    fn capture_selection(&self) -> Result<String, String> {
        // Mac AXUIElement hooks
        Ok("Sample captured text from macOS AXUIElement".to_string())
    }
}
