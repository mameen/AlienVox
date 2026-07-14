# AlienVox Technology Options: Core Systems & Local Neural TTS

This document serves as the comprehensive technical evaluation of native OS Speech Engines and Edge-capable ML/AI Text-to-Speech models for **AlienVox**.

---

## 1. Windows Native Speech Subsystems

To maintain our targeted **sub-150ms execution latency** with zero operational overhead, the local Windows framework options must run natively using explicit platform APIs via the `windows-sys` or `windows` crates.

| Engine Platform | API Hook Layer | Architecture Status | Technical Assessment |
| :--- | :--- | :--- | :--- |
| **SAPI 4** | Legacy COM Interfaces | Obsolete (Legacy Win9x/XP) | Not viable. Out of production, lacks modern 64-bit calling conventions, and suffers from unnatural, highly robotic robotic phoneme blending. |
| **SAPI 5** | `ISpVoice` COM Registry | **Supported Fallback** | Standard Windows desktop TTS interface. Extremely fast instantiation (< 20ms), tiny runtime footprint, but audio profiles (e.g., *Microsoft David/Hazel/Zira*) sound dated. |
| **Microsoft Speech Platform** | Server COM (`HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech Server\v11.0`) | **Supported** | Originally built for enterprise server environments. Extends SAPI5-like efficiency but allows access to higher-fidelity runtime language packs and specific automated registry paths. |
| **Windows.Media.SpeechSynthesis (WinRT)** | WinRT Runtime Component (`SpeechSynthesizer`) | **Primary Desktop Choice** | Modern Windows 10/11 native architecture. Provides cleaner multi-threaded execution, accessibility hook synchronization, and utilizes improved voices (e.g., *Microsoft George, Susan*). |

---

## 2. macOS Native Speech Subsystems

On Apple ecosystems, the runtime execution shifts away from COM abstractions and directly uses the native Objective-C/Swift frameworks via low-level Mach messaging bridges.

* **AVFoundation Engine (`AVSpeechSynthesizer`):** This is the modern, primary framework interface. By instantiating an `AVSpeechUtterance` inside Rust (bridged through the `objc` or `cocoa` crates), the app can tap into local voice profiles (like *Siri*, *Alex*, or customized premium accessibility packs).
* **Personal Voice (macOS 14+ / 15+):** Utilizing `AVSpeechSynthesizer.requestPersonalVoiceAuthorization`, AlienVox can safely trigger user-cloned neural speech profiles directly at the hardware layer without passing any audio processing down to a remote server cloud.

---

## 3. High-Efficiency Local Neural ML Models (For the `models/` Directory)

To provide premium, modern neural-sounding voices without adding an external Python runtime layer, models must be executable via native inference engines like **ONNX Runtime** (via the `ort` Rust crate), **Candle** (Hugging Face pure-Rust ML engine), or **llama.cpp** bindings.

### A. Kokoro-82M (The Edge Standard)
* **GitHub Repository:** [hexgrad/kokoro](https://github.com/hexgrad/kokoro)
* **Architecture:** Decoder-only StyleTTS2 + ISTFTNet (No heavy diffusion or auto-regressive audio tokens).
* **Parameters & Footprint:** **82 Million Parameters**. Binary weights fit cleanly inside a single file under **330MB**.
* **Ecosystem Popularity:** Extremely high. Actively ranks at the top of community TTS naturalness arenas (Hugging Face Spaces) relative to its physical compute footprint.
* **Performance Benchmark:** Blazing fast. Capable of generating speech at **5x to 15x faster than real-time** on mid-tier hardware. Can be executed seamlessly on a raw CPU thread without needing an active dedicated GPU.
* **License:** **Apache 2.0** (Commercially viable, zero legal or enterprise friction).

### B. Chatterbox-Turbo
* **GitHub Repository:** Provided via [Resemble-AI/chatterbox](https://github.com/resemble-ai/chatterbox)
* **Architecture:** Distilled Single-Step Decoder (Reduces inference operations down from 10 steps to 1).
* **Parameters & Footprint:** **~350 Million Parameters** (Weights scale around 1.2GB).
* **Ecosystem Popularity:** Rapidly growing standard for low-latency interactive conversational voice loops.
* **Performance Benchmark:** Displays an ultra-low execution latency profile (~75ms initialization window). Achieves a massive 65% win rate in subjective head-to-head evaluations against commercial streaming cloud runtimes. 
* **Special Subsystems:** Built-in semantic emotional markup natively processing token streams containing paralinguistic tags like `[laugh]`, `[cough]`, `[whisper]`, or `[sigh]`.
* **License:** **MIT** (Fully open, modification and commercial encapsulation permissible).

### C. Piper TTS
* **GitHub Repository:** [rhasspy/piper](https://github.com/rhasspy/piper)
* **Architecture:** VITS-based end-to-end architecture optimized explicitly for low-resource hardware targets.
* **Parameters & Footprint:** Highly granular scaling profiles from Vellum Tiny (**~15MB**) up to High Quality (**~150MB** per voice file).
* **Ecosystem Popularity:** Universal standard for local home automation, offline open-source screen readers, and embedded micro-controllers.
* **Performance Benchmark:** Fully optimized for low-end ARM chips and classic desktop CPUs. It generates clear, slightly robotic but highly legible speech instantly. 
* **Integration Strategy:** Native C++ core engine makes it incredibly straightforward to drop a pre-compiled `piper` static library straight into our Rust build compilation script.
* **License:** **MIT** (Commercially safe, friendly tracking constraints).

---

## 4. Architectural Implementation Strategy

```text
[Text Selection] ➔ [Rust Main Thread] ➔ ──(Route Check)──➔ Option 1: Native WinRT/AVFoundation (Latency: <30ms)
                                       └──➔ Option 2: Local models/ (ONNX/ort)   (Latency: <120ms)
```

1. **The Core Strategy:** All models placed into the `models/` folder are converted directly to **ONNX formats** or raw tensor weights (`.safetensors`).
2. **Execution Context:** The Rust application reads these files dynamically using the `ort` runtime wrapper crate, completely passing over the need for any internal Python interpreter loop.
