#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Serialize, Deserialize, Clone, Debug)]
struct VoiceInfo {
    name: String,
    language: String,
    gender: String,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
struct AudioSettings {
    rate: i32,
    pitch: i32,
    volume: u8,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
struct DocumentState {
    filename: String,
    content: String,
    cursor_line: usize,
    cursor_column: usize,
}

#[tauri::command]
fn get_voices() -> Vec<VoiceInfo> {
    // In a real implementation, this would query the system's TTS voices
    vec![
        VoiceInfo {
            name: "Zira".to_string(),
            language: "English (United States)".to_string(),
            gender: "Female".to_string(),
        },
        VoiceInfo {
            name: "David".to_string(),
            language: "English (United States)".to_string(),
            gender: "Male".to_string(),
        },
        VoiceInfo {
            name: "Hedda".to_string(),
            language: "German".to_string(),
            gender: "Female".to_string(),
        },
        VoiceInfo {
            name: "Marie".to_string(),
            language: "French".to_string(),
            gender: "Female".to_string(),
        },
    ]
}

#[tauri::command]
fn get_audio_settings() -> AudioSettings {
    AudioSettings {
        rate: 0,
        pitch: 0,
        volume: 100,
    }
}

#[tauri::command]
fn update_audio_settings(rate: i32, pitch: i32, volume: u8) -> Result<(), String> {
    // In a real implementation, this would update the TTS engine settings
    println!("Updating audio settings - Rate: {}, Pitch: {}, Volume: {}", rate, pitch, volume);
    Ok(())
}

#[tauri::command]
fn new_document() -> DocumentState {
    DocumentState {
        filename: "Document1".to_string(),
        content: "".to_string(),
        cursor_line: 1,
        cursor_column: 1,
    }
}

#[tauri::command]
fn open_document(path: String) -> Result<DocumentState, String> {
    let file_path = PathBuf::from(&path);
    if !file_path.exists() {
        return Err(format!("File not found: {}", path));
    }
    
    let content = std::fs::read_to_string(file_path.clone())
        .map_err(|e| format!("Failed to read file: {}", e))?;
    
    Ok(DocumentState {
        filename: file_path.file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string(),
        content,
        cursor_line: 1,
        cursor_column: 1,
    })
}

#[tauri::command]
fn save_document(content: String, path: Option<String>) -> Result<(), String> {
    let file_path = match path {
        Some(p) => PathBuf::from(&p),
        None => {
            // In a real implementation, this would open a save dialog
            return Err("No file path provided".to_string());
        }
    };
    
    std::fs::write(&file_path, content)
        .map_err(|e| format!("Failed to write file: {}", e))?;
    
    Ok(())
}

#[tauri::command]
fn speak_text(_text: String, voice: String, rate: i32, pitch: i32, volume: u8) -> Result<(), String> {
    // In a real implementation, this would use the Windows TTS API
    println!("Speaking text with voice: {}, rate: {}, pitch: {}, volume: {}", 
             voice, rate, pitch, volume);
    Ok(())
}

#[tauri::command]
fn stop_speaking() -> Result<(), String> {
    // In a real implementation, this would stop the TTS engine
    println!("Stopping speech");
    Ok(())
}

#[tauri::command]
fn pause_speaking() -> Result<(), String> {
    // In a real implementation, this would pause the TTS engine
    println!("Pausing speech");
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            get_voices,
            get_audio_settings,
            update_audio_settings,
            new_document,
            open_document,
            save_document,
            speak_text,
            stop_speaking,
            pause_speaking,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri process");
}
