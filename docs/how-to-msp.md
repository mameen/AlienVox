# How to Use Microsoft Speech Platform 11 for TTS and STT with Ozeki VoIP SIP SDK

Source: https://voip-sip-sdk.com/p_7563-how-to-use-microsoft-speech-platform-11-for-tts-and-stt.html

## Overview

This guide explains how to integrate Microsoft Speech Platform (version 11) text-to-speech (TTS) and speech-to-text (STT) capabilities into a softphone or other application built on the Ozeki VoIP SIP SDK.

**Use cases:**
- Text-to-speech: reading typed text aloud — useful for enabling a mute person to participate in voice calls, or for IVR systems where menu options are read aloud automatically.
- Speech-to-text: converting spoken words into text — useful for letting a deaf person follow a live voice call in written form.

## Requirements

Download and install:
- Microsoft Speech Platform SDK (version 11)
- Microsoft Speech Platform Runtime (version 11)
- The `msp-11.zip` package, which contains two helper classes:
  - `MSSpeechPlatformSTT` — handles speech recognition
  - `MSSpeechPlatformTTS` — handles text-to-speech

Note: during installation, language packs are labeled either "SR" (Speech Recognition) or "TTS" (Text-To-Speech) depending on their purpose.

## Setup Steps

1. Install the Microsoft Speech Platform SDK and Runtime.
2. Add the two classes from `msp-11.zip` to your Visual Studio project.
3. In your project, add references to:
   - The Ozeki VoIP SIP SDK (`ozeki.dll`)
   - `Microsoft.Speech.dll`
4. If building a 64-bit project, make sure "Prefer 32-bit" is **unchecked** in project properties (Build tab) — leaving it checked can cause errors.

## Implementation

**Text-to-Speech:**
- Call `AddTTSEngine()` on a `TextToSpeech` object, passing in a new `MSSpeechPlatformTTS` instance.
- Use `GetAvailableVoices()` to list available voices.
- Use `ChangeLanguage()` to select the voice/language you want.

**Speech-to-Text:**
- Assign a new `MSSpeechPlatformSTT` instance as the engine via `ChangeSTTEngine()` on a `SpeechToText` object.
- Use `GetRecognizers()` to list available recognizers.
- Use `ChangeRecognizer()` to select the one you want.

## Example (C#)

```csharp
using System;
using System.Threading;
using Ozeki.Media;

namespace Microsoft_Speech_Platform
{
    class Program
    {
        static Speaker _speaker;
        static Microphone _microphone;
        static MediaConnector _connector;
        static TextToSpeech _tts;
        static SpeechToText _stt;

        static void Main(string[] args)
        {
            _microphone = Microphone.GetDefaultDevice();
            _speaker = Speaker.GetDefaultDevice();
            _connector = new MediaConnector();

            SetupTextToSpeech();
            SetupSpeechToText();

            while (true) Thread.Sleep(10);
        }

        static void SetupTextToSpeech()
        {
            _tts = new TextToSpeech();
            _tts.AddTTSEngine(new MSSpeechPlatformTTS());

            var voices = _tts.GetAvailableVoices();
            foreach (var voice in voices)
            {
                if (voice.Language.Equals("en-GB"))
                    _tts.ChangeLanguage(voice.Language, voice.Name);
            }

            _speaker.Start();
            _connector.Connect(_tts, _speaker);
            _tts.AddAndStartText("Hello World!");
        }

        static void SetupSpeechToText()
        {
            string[] words = { "Hello", "Welcome" };
            _stt = SpeechToText.CreateInstance(words);
            _stt.WordRecognized += stt_WordRecognized;
            _stt.ChangeSTTEngine(new MSSpeechPlatformSTT());

            var recognizers = _stt.GetRecognizers();
            foreach (var recognizer in recognizers)
            {
                if (recognizer.Culture.Name == "en-GB")
                    _stt.ChangeRecognizer(recognizer.ID);
            }

            _connector.Connect(_microphone, _stt);
            _microphone.Start();
        }

        static void stt_WordRecognized(object sender, SpeechDetectionEventArgs e)
        {
            Console.WriteLine("Word recognized: {0}", e.Word);
        }
    }
}
```

## Available Languages

**Text-to-Speech engines:** Chinese (Hong Kong, PRC, Taiwan), Danish, Dutch, English (Australia, Canada, India, UK, US, US Zira Pro), Finnish, French (Canada, France), German, Italian, Japanese, Korean, Norwegian, Polish, Portuguese (Brazil, Portugal), Russian, Spanish (Catalan, Mexico, Spain), Swedish.

**Speech-to-Text engines:** German, British English, US English, Mexican Spanish, Canadian French, French.

## Related Resources

- How to use TextToSpeech (general)
- How to implement Voice Recognition (general)
- Ozeki VoIP SDK documentation home
