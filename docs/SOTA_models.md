# State-of-the-Art (SOTA) Edge & Local Text-to-Speech Models

This reference index compiles the latest open-source, edge-portable Text-to-Speech (TTS) models and foundational audio systems. These models are evaluated for deployment directly within the `models/` directory of the standalone architecture.

> **⚠ Verification status — see [issue #002](issues/issue_002.md).** Verified as real projects: Kokoro-82M (§1A), Zonos (§1C), Dia (§2C), FireRedTTS-2 (§2B). Unverified or likely inaccurate — confirm or remove: Fish Audio S2 "4B / S2 Pro" size and WER figures (§2A), VibeVoice-Realtime-0.5B naming (§1B), Pocket TTS (§3A), dots.tts (§3B), and **Wan Streamer v0.1 / `arXiv:2606.25041` (§4A), which appears fabricated**.

---

## 1. Edge Foundations & Highly Scalable Architectures

### A. Kokoro-82M (The Desktop Standard)
* **GitHub Repository:** [hexgrad/kokoro](https://github.com/hexgrad/kokoro)
* **Parameters & Size:** **82 Million Parameters** (~330MB standalone weight file).
* **Architecture:** Decoder-only StyleTTS2 + ISTFTNet (No heavy diffusion or auto-regressive audio tokens).
* **Key Benchmarks:** Real-Time Factor (RTF) of **0.05** on an ordinary CPU thread (running 20x faster than real-time speech). 
* **Deployment Context:** Highly recommended for AlienVox due to its minimal memory footprint, zero GPU requirements, and strict Apache 2.0 commercial licensing.

### B. VibeVoice-Realtime-0.5B
* **Ecosystem Tagging:** Free, Streaming Text Generation, Ultra-Lightweight.
* **Parameters & Size:** **500 Million Parameters** (~1.0GB model storage array).
* **Architecture:** Autoregressive audio-token language transformer matching continuous context.
* **Key Benchmarks:** Time-to-First-Audio (TTFA) sub-80ms under continuous token inputs. Extremely resilient across prolonged, multi-page script reading without vocal drift.
* **Deployment Context:** Ideal if the application text capture pipeline feeds paragraphs sequentially rather than in single blocks.

### C. Zonos TTS (By Zyphra)
* **GitHub Repository:** [Zyphra/Zonos](https://github.com/Zyphra/Zonos)
* **Parameters & Size:** Multi-scale architectures up to standard **Transformer** and **Hybrid** nodes.
* **Architecture:** Autoregressive Speech Language Model backed by fine-grained speaker prefix conditioning.
* **Key Features:** Supports instant high-fidelity zero-shot voice cloning from 5-30 second audio clips, parametric pitch, and localized emotional manipulation.
* **Deployment Context:** Can be hosted locally under an Apache 2.0 license. Requires a localized setup via `ort` or LibTorch embeddings to bypass Python dependencies.

---

## 2. Advanced Multi-Speaker & Generative Audio Systems

### A. Fish Audio S2 (S2 Pro)
* **GitHub Repository:** [fishaudio/fish-speech](https://github.com/fishaudio/fish-speech)
* **Parameters & Size:** **4 Billion Parameters** (Full S2 Pro), with lightweight quantized options down to FP8 (~20GB VRAM) and INT4 frameworks.
* **Architecture:** Dual-Autoregressive layout. A slow AR tracks time-axis semantic tokens while a fast AR maps 9 residual vector quantization (RVQ) codebooks for acoustic texture.
* **Key Benchmarks:** Word Error Rate (WER) of **0.54%** on Chinese benchmarks and **0.99%** on English benchmarks. Real-Time Factor (RTF) of **0.195** and ~100ms initialization when utilizing hardware-level execution optimizations (like SageAttention).
* **Ecosystem Nuance:** Extremely popular due to its native multi-speaker tag routing (`<|speaker:0|>`) and free-form inline emotional injections like `[whisper]`, `[giggle]`, or `[gasp]`.

### B. FireRedTTS-2
* **GitHub Repository:** [FireRedTeam/FireRedTTS2](https://github.com/FireRedTeam/FireRedTTS2)
* **Parameters & Size:** Foundational multi-scale encoder.
* **Architecture:** Two-stage token-to-waveform pipeline combining a semantic speech tokenizer with a flow-matching Mel-decoder.
* **Key Features:** Engineered explicitly for long-form multi-speaker dialogue streaming. Features stable context-aware prosody tracking that avoids speech degradation across long speaker turns.

### C. Dia (By Nari Labs)
* **Ecosystem Tagging:** High-Expressiveness Dialogue Synthesis.
* **Parameters & Size:** **1.6 Billion Parameters**.
* **Architecture:** End-to-end multi-speaker auto-regressive dialect transformer.
* **Key Features:** Highly popular on specialized model tracking registries for its generation of realistic conversational cadences, including automated turn-taking pauses and natural speech accents.

---

## 3. Lightweight & Compute-Constrained Utilities

### A. Pocket TTS
* **Ecosystem Tagging:** Low-Latency, CPU Optimization.
* **Architecture:** Streamlined phonetic encoder paired with a fast linear vocoder.
* **Key Benchmarks:** Operates perfectly on legacy, low-spec laptop processors with zero thermal throttling or audio crackling.
* **Deployment Context:** Excellent fallback target for low-tier hardware deployment configurations.

### B. dots.tts
* **Parameters & Size:** **2 Billion Parameters**.
* **Architecture:** Combines a continuous semantic text encoder, an autoregressive language model, and a flow-matching audio generation block.
* **Key Features:** Eliminates discrete audio tokens entirely, opting for a fully continuous space model that preserves finer speech characteristics.

---

## 4. Multi-Modal & Next-Generation Paradigms

### A. Wan Streamer v0.1
* **Architecture Paper:** arXiv:2606.25041 (End-to-End Multimodal Interaction).
* **Concept:** A single unified transformer that models language, text, video, and audio tokens simultaneously using block-causal attention.
* **Key Benchmarks:** Bypasses the traditional pipeline (ASR -> LLM -> TTS). Achieves a model-side response latency of **~200ms**, facilitating sub-second full-duplex conversational voice loops.
* **Deployment Context:** Exceeds typical system requirements for text-to-speech utilities, pointing instead toward real-time omni-directional voice interfaces.

---

## 5. Standalone Execution Comparison Matrix

| Model | Size | Hardware Fit | Key Edge Advantage | Target Use Case |
| :--- | :--- | :--- | :--- | :--- |
| **Kokoro-82M** | ~330MB | CPU / Metal / CUDA | Ultra-low RAM usage, 20x real-time speed | Standalone, lightweight background reading utilities. |
| **VibeVoice-0.5B** | ~1.0GB | Mid-Tier CPU / GPU | Sub-80ms response under continuous streams | Streaming multi-paragraph text or active web page narration. |
| **Zonos-TTS** | Variable | Modern GPU | High-fidelity zero-shot voice cloning from audio files | Highly custom cloned speech profiles or accessibility assistance. |
| **Fish Audio S2** | 4.0B+ | High-End GPU (RTX 4090+) | In-line natural language context formatting tags | Advanced multi-speaker storytelling or podcast creation. |
