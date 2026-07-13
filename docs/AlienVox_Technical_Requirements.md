# Technical Requirements Document (TRD)
## Project "AlienVox": Cross-Platform Minimalist Read-Selection Utility

| Attribute | Specification |
| :--- | :--- |
| **Company** | AlienTech.Software |
| **Author** | Product Engineering Team |
| **Date** | July 13, 2026 |
| **Status** | Draft / Review |
| **Version** | v1.0 |
| **Target OS** | Windows 11 / macOS 14+ |
| **Core Focus** | Accessibility, Ultra-low Latency, Simplicity |

---

## 1. Executive Summary & Problem Statement

Operating systems have increasingly coupled Text-to-Speech (TTS) engine pipelines with complex screen readers (e.g., Windows Narrator) or heavy context-aware layout parsers (e.g., Microsoft Edge Read Aloud). As a result, Windows lacks a native, friction-free, universal "Speak Selection" tool equivalent to macOS's long-standing system feature[cite: 1]. 

**AlienVox** is a lightweight, cross-platform background application (Windows & macOS) engineered by AlienTech.Software to solve this exact gap[cite: 1]. Its core thesis is absolute predictability: highlight content, trigger a global shortcut, and immediately hear exactly what is selected—no extra paragraphs, no UI wrappers, and no unwanted orchestration[cite: 1].

---

## 2. Core Philosophy & Design Goals

*   **Frictionless Execution:** Zero configuration required for the primary path. The global hotkey must feel like a native feature, matching the effortless nature of `Option + Esc` on Mac.
*   **Strict Respect for Selection:** The utility must only speak the active context block. If text is explicitly highlighted, nothing else is spoken.
*   **Hybrid Audio Pipeline:** Utilize local, zero-latency system APIs for instantaneous offline playback, with a clean path to high-fidelity cloud/AI voice providers when online.
*   **Unobtrusive Presence:** The application lives completely in the Windows System Tray and macOS Status Menu Bar. No active window footprint during operation.

---

## 3. Functional & Technical Requirements

### 3.1 Global Hotkey & Content Capture Architecture
The application must continuously listen for a customizable global hotkey (Default: `Ctrl + Esc` or `Alt + Esc` on Windows; `Option + Esc` on macOS) even when running completely in the background. 

Upon activation, the capture pipeline must execute a non-destructive context fetch. The system must inspect the OS clipboard and active window memory space using a three-tier fallback approach:

1.  **Active Selection Capture (Tier 1):** Dynamically invoke native accessibility hooks (`UI Automation` on Windows; `AXUIElement` on macOS) to fetch the exact text span currently highlighted by the user.
2.  **Fallback Clipboard Extraction (Tier 2):** If UI Automation returns empty or fails within a 50ms window, simulate a rapid copy command (`Ctrl + C` / `Cmd + C`) to read multi-format clipboard registers, capturing raw Text, Rich Text Format (RTF), or layout metadata.
3.  **Image/OCR Processing (Tier 3):** If the clipboard contains bitmap/image data (e.g., a cropped screenshot), route the buffer instantly into a local, lightweight OCR engine (`Windows.Media.Ocr` or macOS `Vision Framework`) to convert pixel-mapped strings to readable text streams.

> ⚠️ **Critical Performance Requirement**
> The total latency from the moment the global hotkey is pressed to the initiation of audio synthesis must not exceed **150 milliseconds** when running on a local engine.

### 3.2 Cross-Platform Tray / Status Menu Interface
The app must lack a traditional main UI window, instead exposing configurations exclusively via native menu anchors (System Tray on Windows, Menu Bar on macOS).

| Module | Functional Specification | Priority |
| :--- | :--- | :--- |
| **System Tray Menu** | Right-clicking/clicking the icon brings up a minimalist native context menu with sliding adjusters for Voice Rate (Speed), Volume, and Engine Selection. | **Critical** |
| **Audio Interruption** | Pressing the global hotkey *while audio is playing* must instantly terminate the current audio thread (Stop playback). Triggering it again begins reading new text. | **Critical** |
| **Voice Profiles** | Support selection between Local Offline OS Engines (SAPI5/Windows Media Synthesis, macOS AVFoundation) and Modern Cloud AI Engines (e.g., OpenAI TTS API, ElevenLabs) via API key injection. | **High** |

---

## 4. Non-Functional Requirements & Technical Stack Recommendations

*   **Framework Options:** 
    *   *Option A (Recommended):* **Rust with Tauri**. Highly recommended for achieving sub-10MB idle memory footprints, excellent security, and clean, native system tray hooks on both platforms.
    *   *Option B:* A lightweight C#/.NET Core background app for Windows paired with a Swift/AppKit companion wrapper for macOS.
*   **State Preservation:** All configuration variables (playback speeds, selected voice, API tokens, global hotkeys) must be stored locally via an encrypted JSON structure or local OS keychain abstractions.
*   **Privacy & Security:** No text captured from selection or clipboard should ever be logged, cached, or persisted locally. If a Cloud AI engine is selected, data transmission must happen via secure TLS streams directly to the provider endpoint without intermediary proxies.
