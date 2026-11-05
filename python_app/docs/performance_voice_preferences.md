# Developer TTS voice preferences

**These ratings are highly subjective.** They record the developer's listening preferences and are a shortlist for personal use, not objective speech-quality measurements. They come from the English performance report `20261105025132`; its timing results mix cold-start and warm runs, so use the ratings to identify voices to audition, not to make precise speed claims.

## ML preferences at the ratings export snapshot

| Model | Developer rating | Preferred voices | Resources and observed latency | Offline sample |
|---|---:|---|---|---|
| **Supertonic 3** | 4.4/5 average across rated voices | F1, F2, F3, and F4 each received 5/5. | About 400 MB of model files; ONNX CPU path. F4 took 1.86 s to synthesize 7.66 s of audio in the historical run. CPU percentage was not measured reliably. | [F1](../install/assets/audio/ml/supertonic3/F1.mp3)<br>[F2](../install/assets/audio/ml/supertonic3/F2.mp3)<br>[F3](../install/assets/audio/ml/supertonic3/F3.mp3)<br>[F4](../install/assets/audio/ml/supertonic3/F4.mp3) |
| **Kokoro-82M** | 4.14/5 average across rated voices | af_heart and bf_emma received 5/5; am_adam also received 5/5 in the old export, and bm_george received 4/5. af_heart remains the default favorite. | About 300 MB shared model files. The af_heart cold-start row added about 1.44 GB RSS and took 26.7 s; warm rows were much lower. Historical run was CUDA-selected, so this does not predict CPU RAM. | [af_heart](../install/assets/audio/ml/kokoro/af_heart.mp3)<br>[am_adam](../install/assets/audio/ml/kokoro/am_adam.mp3)<br>[bf_emma](../install/assets/audio/ml/kokoro/bf_emma.mp3)<br>[bm_george](../install/assets/audio/ml/kokoro/bm_george.mp3) |
| **Piper** | 4.0/5 average across rated voices | **All six are now developer favorites (“really good”).** Historical scores: Ryan High 5/5; Lessac Medium, Amy Medium, Kathleen Low, Southern English Female Low, and Jenny Dioco Medium each 4/5. | ONNX CPU inference. Ryan High is about 126 MB; the two Low-tier voices are about 20 MB each; Medium voices are about 63 MB each. | [Lessac](../install/assets/audio/ml/piper/en_US-lessac-medium.mp3)<br>[Amy](../install/assets/audio/ml/piper/en_US-amy-medium.mp3)<br>[Ryan High](../install/assets/audio/ml/piper/en_US-ryan-high.mp3)<br>[Kathleen Low](../install/assets/audio/ml/piper/en_US-kathleen-low.mp3)<br>[Southern English Female Low](../install/assets/audio/ml/piper/en_GB-southern_english_female-low.mp3)<br>[Jenny Dioco](../install/assets/audio/ml/piper/en_GB-jenny_dioco-medium.mp3) |

## Follow-up Piper listening notes

The developer now describes all six of these Piper voices as **really good**: [en_US-lessac-medium](../install/assets/audio/ml/piper/en_US-lessac-medium.mp3), [en_US-amy-medium](../install/assets/audio/ml/piper/en_US-amy-medium.mp3), [en_US-ryan-high](../install/assets/audio/ml/piper/en_US-ryan-high.mp3), [en_US-kathleen-low](../install/assets/audio/ml/piper/en_US-kathleen-low.mp3), [en_GB-southern_english_female-low](../install/assets/audio/ml/piper/en_GB-southern_english_female-low.mp3), and [en_GB-jenny_dioco-medium](../install/assets/audio/ml/piper/en_GB-jenny_dioco-medium.mp3). This latest qualitative endorsement applies to all six; the 4/5 and 5/5 scores above remain the historical ratings export values.

## Follow-up Kokoro listening notes

These qualitative notes are newer than the numeric ratings export and reflect the developer's latest listening:

- **Fantastic:** [af_heart](../install/assets/audio/ml/kokoro/af_heart.mp3), [af_bella](../install/assets/audio/ml/kokoro/af_bella.mp3), and [bf_emma](../install/assets/audio/ml/kokoro/bf_emma.mp3).
- **Not too bad:** [bm_george](../install/assets/audio/ml/kokoro/bm_george.mp3) and [am_adam](../install/assets/audio/ml/kokoro/am_adam.mp3).

The previous export scored am_adam 5/5. This newer note supersedes that numeric score as the current qualitative preference; the exported JSON remains the unmodified historical snapshot.

## SAPI voices in the developer shortlist (not scored)

The exported ratings contain no SAPI star scores, so these remain subjective audition candidates. **SAPI-only performance recommendation: MSTTS_V110_enUS_ZiraM.** It synthesized the canonical phrase in 9.27 s versus 9.92 s for TTS_MS_EN-US_ZIRA_11.0 in the historical report. That is a latency choice, not a confirmed quality win. It does not change the overall ML default (Kokoro af_heart). Captured samples are **WAV** files, not bundled MP3s.

| SAPI voice | Performance / preference | Resources | Offline sample |
|---|---|---|---|
| MSTTS_V110_enUS_ZiraM | **SAPI-only recommended candidate**; 9,267 ms; no star rating. | Windows-provided voice; no bundled ML model files. | [Zira OneCore WAV](../.logs/20261105025132_samples/sapi5/MSTTS_V110_enUS_ZiraM.wav) |
| TTS_MS_EN-US_ZIRA_11.0 | 9,925 ms; no star rating. | Windows-provided voice; no bundled ML model files. | [Zira Speech WAV](../.logs/20261105025132_samples/sapi5/TTS_MS_EN-US_ZIRA_11.0.wav) |
| MSTTS_V110_enGB_HazelM | 11,156 ms; no star rating. | Windows-provided voice; no bundled ML model files. | [Hazel WAV](../.logs/20261105025132_samples/sapi5/MSTTS_V110_enGB_HazelM.wav) |
| MSTTS_V110_enGB_SusanM | 11,138 ms; no star rating. | Windows-provided voice; no bundled ML model files. | [Susan WAV](../.logs/20261105025132_samples/sapi5/MSTTS_V110_enGB_SusanM.wav) |

## Resource-data caveat

The old report cannot rank CPU use: its CPU-percent readings are all 0, and the harness only takes before/after non-blocking snapshots rather than interval or peak samples. Its `memory_mb` is process RSS change across the request, not total or peak RAM, and first-use model loading is included. The report also records the globally selected device, which can say `cuda` even for CPU-only ONNX engines. Weight sizes above are on-disk estimates from the app catalog, not RAM requirements. A clean CPU-only run with interval-based CPU sampling and peak-RSS tracking is needed for a fair runtime comparison.

## Source and scope

Scores are copied from `alienvox-performance-ratings-20261105025132.json`. Each voice score is the developer's 1-to-5 listening rating; model averages are averages of its rated voices. The historical report used the same English phrase for its rows. Scores may change after listening to the locale-matched samples in the newer phrase catalog.
