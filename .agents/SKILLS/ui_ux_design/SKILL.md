---
name: ui-ux-design
description: UI/UX design guidelines for AlienVox. Defines the classic Win32/WPF functional aesthetic, layout hierarchy, menu bar, system tray behavior, and iconography, plus how to brief an LLM to generate matching interfaces.
license: Apache-2.0
compatibility: Cross-platform environment (Windows 11 / macOS 14+)
metadata:
  author: AlienTech.Software
  version: "1.0"
---

# UI/UX Design Guidelines

This skill codifies the visual language, layout hierarchy, and component vocabulary for AlienVox surfaces. AlienVox is **system-tray-first**: there is no persistent main window during normal use. When a settings/preferences panel *is* opened, it follows the classic, highly functional desktop aesthetic described below (reference: the Balabolka TTS utility).

> **Testing vs. end state:** The current main window — the full Balabolka-style text canvas in Section 2 — is a **temporary testing harness** used during development to exercise the speech pipeline. It is **not** the shipped UI. In the production build it is removed; the only persistent window is the **Preferences** panel (Section 2.5), opened on demand from the tray. Build the Section 2 surface for testing, but never treat it as the final interface.

## 1. Design Aesthetic

- **Style:** Traditional, highly functional desktop interface matching the native Windows Classic/Forms look (Win32/WPF layout). Maximize workspace utility — prioritize explicit control buttons, tabbed configurations, and sliders over modern minimalist whitespace.
- **Density over decoration:** Controls are compact, labeled, and always visible. Avoid hidden gestures or ambiguous affordances.
- **Determinism:** Every control maps to one explicit action. No speculative or decorative UI ("no ghost abstractions").
- **Cross-platform parity:** The same layout hierarchy applies on Windows 11 and macOS 14+, rendered through the native webview per the Rust + Tauri stack.

## 2. Reference Interface Breakdown

> **Scope note:** Sections 2.1–2.4 describe the **testing harness** main window. It is temporary and exists only to validate the speech pipeline during development. The end-state production surface is Section 2.5 (Preferences) only.

### 2.1 Menu Bar & Primary Toolbar (Top Layer)
- **Window title:** `AlienVox - [Document1]` with standard OS window controls (Minimize, Maximize, Close) top-right.
- **Classic text menu bar:** `File, Edit, Text, Speech, Voice, Options, View, Tools, Bookmark, Help`.
- **Action toolbar icons:** a row of square, flat 2D utility icons:
  - **File operations:** New File, Open, Save, Split Text, Convert to Audio File.
  - **Playback engine controls:** green Play triangle, gray Pause parallel block, red Stop square.
  - **Text utilities:** Find text, Spellcheck, Voice adjustment parameters.

### 2.2 Engine Tabs & Voice Controls (Middle Layer)
- **Tabbed framework:** block tabs to switch speech platforms — `SAPI 4`, `SAPI 5`, `Microsoft Speech Platform` (and AlienVox cloud/ML engine tabs).
- **Voice dropdown:** full-width horizontal dropdown below the tabs to pick the installed voice font/model, flanked by `About` and `Select Voice` buttons.
- **Audio modulation sliders:** a grid of three horizontal sliders with numerical tick marks:
  - **Rate:** default-centered at `0` (range −10 to 10).
  - **Pitch:** default-centered at `0` (range −10 to 10).
  - **Volume:** default at maximum `100` (range 0 to 100).

### 2.3 Main Workspace & Text Canvas (Core Body)
- **Text editor input:** a large, stark-white multi-line `TextArea` occupying ~80% of the vertical space, with a flashing cursor at line 1, column 1, awaiting text injection or clipboard paste.

### 2.4 Status Bar & Metadata (Bottom Layer)
- **Document tabs:** notebook-style tabs bottom-left tracking open buffers (e.g., `Document1`).
- **Information bar:** split status strip showing `Line: Column` telemetry (e.g., `1: 1`).

### 2.5 Preferences Panel (End-State Window)
This is the **only** window that ships in the production build. Everything in 2.1–2.4 is the testing harness and is dropped once the pipeline is proven.
- **Scope:** engine/provider selection, voice pick, Rate/Pitch/Volume controls, global hotkey binding, and startup/tray options — nothing more.
- **No text canvas:** the large editor area (2.3) and document tabs (2.4) do **not** appear in production; speech always operates on the live OS text selection captured via the hotkey.
- **Invocation:** opened only via the tray `Settings…` item; closing returns to the tray. It never becomes a persistent main window.

## 3. System Tray

AlienVox lives primarily in the system tray. The tray is the default entry point; windows are opened on demand.

- **Tray icon:** always present while the app runs; reflects state (idle, speaking, error) via distinct icon variants.
- **Left-click:** primary action (toggle speak / stop the current utterance).
- **Right-click context menu:** explicit, flat, text-labeled items in a fixed order:
  - `Speak Selection`, `Stop`
  - `Voice ▸` (submenu of installed voices/engines)
  - `Settings…` (opens the Preferences panel — Section 2.5)
  - `About`
  - `Quit`
- **No forced window:** never spawn a main window on launch or when triggering a speak action. UI panels appear only through explicit tray/menu interaction.
- **Platform mapping:** Windows tray via Win32/WinRT; macOS status-bar item via the `mac` platform path. Behavior and menu order stay identical across platforms.

## 4. Iconography

- **Style:** square, flat 2D icons — no gradients, no skeuomorphism, no drop shadows. Consistent stroke weight and padding across the set.
- **Semantic color reserved for transport controls only:** green Play, gray Pause, red Stop. All other toolbar icons are monochrome/neutral.
- **Consistent shape per type:** one shape vocabulary per action category (file ops, playback, text utilities); do not mix metaphors within a category.
- **Tray icon set:** provide state variants (idle / speaking / error) plus light and dark theme versions, sized for OS tray requirements (Windows 16/32 px, macOS template images).
- **Assets:** ship icons as embedded binary assets baked into the single binary (per the production build model); never load icons from a network source at runtime.

## 5. Briefing an LLM to Generate the Interface

When asking an LLM to generate or replicate an AlienVox surface, provide: (a) the design aesthetic, (b) the layout hierarchy, and (c) the functional components — then name the target UI technology explicitly.

**Suggested prompt template:**

> "Act as a senior front-end engineer. Based on the description above, generate the structural layout and code for a desktop application window matching this classic Windows-forms utility layout. It needs a menu bar, a row of playback controls (Play, Pause, Stop), speech engine tabs (SAPI5 / Cloud Engine), audio sliders for Rate/Pitch/Volume, and a large central text input area. Implement this using **[target: Slint / HTML+Tailwind for the Tauri frontend / WPF]**."

Always state the concrete target technology; never leave the rendering stack ambiguous.

---

## 6. Related Decisions
- See `highlevel_design` skill — single standalone binary and asset embedding (governs how icons and UI assets ship).
- See `workspace-discipline` skill — reflection/self-check and no-ghost-abstraction rules apply to every UI addition.
