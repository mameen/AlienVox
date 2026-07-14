# AlienVox Technology Options: Core Systems & Local Neural TTS

This document serves as the comprehensive technical evaluation of native OS Speech Engines, Edge-capable ML/AI Text-to-Speech models, and free open-source Rust library ecosystems for **AlienVox**.

> **⚠ Verification status — see [issue #002](issues/issue_002.md).** Native OS engines (§1–§2), Kokoro-82M (§3A), and the `tts` crate (§4A) are verified. Unverified / needs correction before being treated as authoritative: Piper voice-tier naming "Vellum Tiny" (§3C), Qwen3-TTS-rs repo/figures (§3B), and the `any-tts` crate plus its "Voxtral" TTS adapter (§4B — Voxtral is ASR, not TTS).

---

## 1. Windows Native Speech Subsystems

To maintain our targeted **sub-150ms execution latency** with zero operational overhead, the local Windows framework options must run natively using explicit platform APIs via the `windows-sys` or `windows` crates.

| Engine Platform | API Hook Layer | Architecture Status | Technical Assessment |
| :--- | :--- | :--- | :--- |
| **SAPI 4** | Legacy COM Interfaces | Obsolete (Legacy Win9x/XP) | Not viable. Out of production, lacks modern 64-bit calling conventions, and suffers from natural, highly robotic phoneme blending. |
| **SAPI 5** | `ISpVoice` COM Registry | **Supported Fallback** | Standard Windows desktop TTS interface. Extremely fast instantiation (< 20ms), tiny runtime footprint, but audio profiles (e.g., *Microsoft David/Hazel/Zira*) sound dated. |
| **Microsoft Speech Platform** | Server COM (`HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech Server\v11.0`) | **Supported** | Originally built for enterprise server environments. Extends SAPI5-like efficiency but allows access to higher-fidelity runtime language packs and automated registry paths. |
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
* **Ecosystem Popularity:** Extremely high. Actively ranks at the top of community TTS naturalness arenas relative to its physical compute footprint.
* **Performance Benchmark:** Blazing fast. Capable of generating speech at **5x to 15x faster than real-time** on mid-tier hardware. Can be executed seamlessly on a raw CPU thread without needing an active dedicated GPU.
* **License:** **Apache 2.0** (Commercially viable, zero legal or enterprise friction).

### B. Qwen3-TTS / Qwen3-TTS-rs
* **GitHub Repository:** [second-state/qwen3_tts_rs](https://github.com/second-state/qwen3_tts_rs)
* **Architecture:** Discrete multi-codebook neural end-to-end codec architecture.
* **Parameters & Footprint:** High performance 0.6B scale models (~1.2GB parameters).
* **Ecosystem Popularity:** Universally recognized as the state-of-the-art layout for minimal first-token latency (~97ms startup execution window).
* **Performance Benchmark:** Highly competitive perceptual audio quality scores matching cloud-hosted APIs, running purely via LibTorch/Candle inside native Rust.
* **License:** Apache 2.0.

### C. Piper TTS
* **GitHub Repository:** [rhasspy/piper](https://github.com/rhasspy/piper)
* **Architecture:** VITS-based end-to-end architecture optimized explicitly for low-resource hardware targets.
* **Parameters & Footprint:** Highly granular scaling profiles from Vellum Tiny (**~15MB**) up to High Quality (**~150MB** per voice file).
* **Ecosystem Popularity:** Universal standard for local home automation, offline open-source screen readers, and embedded micro-controllers.
* **Performance Benchmark:** Fully optimized for low-end ARM chips and classic desktop CPUs. It generates clear, slightly robotic but highly legible speech instantly. 
* **Integration Strategy:** Native C++ core engine makes it incredibly straightforward to drop a pre-compiled `piper` static library straight into our Rust build compilation script.
* **License:** **MIT** (Commercially safe, friendly tracking constraints).

---

## 4. Universal High-Level Open Source Libraries (Option 4)

Instead of building raw OS API wrappers or model inference pipelines completely by hand, AlienVox can utilize existing, open-source Rust crates that encapsulate these pipelines into clean, type-safe high-level libraries.

### A. The `tts` Crate (Unified Native Backend Bridge)
* **Crates.io Registry:** [crates.io/crates/tts](https://crates.io/crates/tts)
* **What it does:** It acts as a cross-platform programmatic abstraction layer over the native OS accessibility systems. Instead of writing separate conditional compilation paths for Windows COM loops and macOS Objective-C objects, you interact with a single unified API.
* **Platform Mapping Under the Hood:**
  * Windows -> Interchanges natively between **WinRT** and screen readers via Tolk.
  * macOS -> Interchanges natively into **AVFoundation/AppKit**.
  * Linux -> Routes via **Speech Dispatcher**.
* **Why use it:** Massively simplifies the initial PoC codebase, completely satisfying our sub-150ms structural window while letting us control speech traits (Rate, Pitch, Volume) out of the box with zero custom OS bindings.

### B. The `any-tts` Framework (Unified Local Neural Runtime)
* **Crates.io Registry:** [crates.io/crates/any-tts](https://crates.io/crates/any-tts)
* **What it does:** A robust, high-level wrapper built directly around HuggingFace's `candle` ML framework to offer a single, unified trait-based API for driving open-source neural models locally.
* **Model Pipeline Integration:** It includes out-of-the-box adapters for **Kokoro-82M**, **Qwen3-TTS**, and **Voxtral**. It handles downloading or searching the `models/` directory natively, spinning up runtime execution seamlessly over CPU, CUDA, or macOS Metal acceleration paths.
* **Why use it:** Completely isolates model-specific tensor mechanics and alignment calculations behind a simple `load_model()` trait interface, keeping the AlienVox runtime fully Python-free.

---

## 5. Architectural Implementation Strategy

```text
[Text Selection] -> [Rust Main Thread] -> --(Route Check)---> Option 1: High-Level `tts` Crate (WinRT/AVFoundation) [Latency: <25ms]
                                       └──-> Option 2: Local models/ (`any-tts` / `ort`)             [Latency: <120ms]
```

1. **The Core Strategy:** All models placed into the `models/` folder are converted directly to ONNX formats or raw tensor weights (.safetensors).
2. **Execution Context:** The Rust application reads these files dynamically using high-level libraries or the `ort` runtime wrapper crate, completely passing over the need for any internal Python interpreter loop.
