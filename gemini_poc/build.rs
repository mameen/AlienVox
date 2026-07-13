fn main() {
    #[cfg(target_os = "windows")]
    {
        let mut res = winres::WindowsResource::new();
        res.set("ProductName", "AlienVox");
        res.set("FileDescription", "AlienVox tray app");
        res.set("OriginalFilename", "alienvox.exe");
        res.set_icon("src/assets/icons/icon.ico");
        res.compile().expect("failed to compile Windows resources");
    }
}
