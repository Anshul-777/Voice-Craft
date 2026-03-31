"""
VoiceCraft Platform — Audio Processor
Handles audio loading, validation, quality assessment, noise reduction,
normalization, segmentation, VAD (Voice Activity Detection).
"""
from __future__ import annotations

import hashlib
import io
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf
from pydub import AudioSegment
from scipy import signal as scipy_signal

# webrtcvad is optional — fallback to energy-based VAD if unavailable
try:
    import webrtcvad
    HAS_WEBRTCVAD = True
except ImportError:
    HAS_WEBRTCVAD = False

logger = logging.getLogger(__name__)

SUPPORTED_INPUT_FORMATS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus"}


@dataclass
class AudioInfo:
    duration_seconds: float
    sample_rate: int
    channels: int
    file_size_bytes: int
    format: str
    snr_db: float
    is_speech_present: bool
    speech_ratio: float          # fraction of audio containing speech
    mean_f0: float | None        # mean fundamental frequency (Hz)
    rms_db: float
    peak_db: float
    sha256: str
    quality_flags: list[str] = field(default_factory=list)

    @property
    def is_acceptable_quality(self) -> bool:
        return (
            self.snr_db >= 10.0
            and self.is_speech_present
            and self.speech_ratio >= 0.30
            and len([f for f in self.quality_flags if "ERROR" in f]) == 0
        )


class AudioProcessor:
    """Enterprise-grade audio processing pipeline."""

    TARGET_SAMPLE_RATE = 22050   # XTTS-v2 native
    VAD_AGGRESSIVENESS = 2       # 0-3; 2 = balanced
    VAD_FRAME_MS = 30            # WebRTC VAD frame size (10, 20, or 30ms)
    MIN_SPEECH_SEGMENT_MS = 500  # discard speech segments shorter than this
    SILENCE_THRESHOLD_DB = -45.0

    def __init__(self) -> None:
        if HAS_WEBRTCVAD:
            self._vad = webrtcvad.Vad(self.VAD_AGGRESSIVENESS)
        else:
            self._vad = None
            logger.warning("webrtcvad not available — using energy-based VAD fallback")

    # ─────────────────────────────────────────────────────────────
    #  Public API
    # ─────────────────────────────────────────────────────────────

    def load_audio(
        self, path: str | Path, target_sr: int = TARGET_SAMPLE_RATE
    ) -> tuple[np.ndarray, int]:
        """
        Load audio from any supported format → mono float32 numpy array.
        Resamples to target_sr.
        """
        path = Path(path)
        suffix = path.suffix.lower()

        if suffix not in SUPPORTED_INPUT_FORMATS:
            raise ValueError(f"Unsupported format: {suffix}")

        # Convert to wav via pydub if not already wav/flac
        if suffix in {".mp3", ".ogg", ".m4a", ".aac", ".wma", ".opus"}:
            wav_bytes = self._convert_to_wav(path)
            y, sr = sf.read(io.BytesIO(wav_bytes))
        else:
            y, sr = sf.read(str(path))

        # Ensure mono
        if y.ndim > 1:
            y = np.mean(y, axis=1)

        # Ensure float32
        y = y.astype(np.float32)

        # Resample if needed
        if sr != target_sr:
            y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
            sr = target_sr

        return y, sr

    def analyze(self, path: str | Path, audio: np.ndarray | None = None, sr: int = TARGET_SAMPLE_RATE) -> AudioInfo:
        """
        Full audio quality analysis.
        Pass pre-loaded audio to avoid double-loading.
        """
        path = Path(path)
        file_size = path.stat().st_size

        if audio is None:
            audio, sr = self.load_audio(path, sr)

        duration = len(audio) / sr
        sha256 = self._sha256_file(path)
        rms_db = self._rms_db(audio)
        peak_db = float(20 * np.log10(np.abs(audio).max() + 1e-9))
        snr = self._estimate_snr(audio, sr)
        speech_frames, speech_ratio = self._vad_analysis(audio, sr)
        mean_f0 = self._estimate_f0(audio, sr) if speech_ratio > 0.1 else None

        flags: list[str] = []
        if duration < 3.0:
            flags.append("WARN: audio shorter than 3s")
        if snr < 5.0:
            flags.append("ERROR: very low SNR — noisy environment")
        elif snr < 10.0:
            flags.append("WARN: low SNR — noise reduction recommended")
        if speech_ratio < 0.20:
            flags.append("ERROR: insufficient speech content")
        if peak_db > -0.5:
            flags.append("WARN: audio may be clipped")
        if rms_db < -35:
            flags.append("WARN: very low volume — check microphone")

        return AudioInfo(
            duration_seconds=round(duration, 3),
            sample_rate=sr,
            channels=1,
            file_size_bytes=file_size,
            format=path.suffix.lstrip(".").upper(),
            snr_db=round(snr, 2),
            is_speech_present=speech_ratio > 0.10,
            speech_ratio=round(speech_ratio, 3),
            mean_f0=round(mean_f0, 2) if mean_f0 else None,
            rms_db=round(rms_db, 2),
            peak_db=round(peak_db, 2),
            sha256=sha256,
            quality_flags=flags,
        )

    def preprocess_for_cloning(
        self,
        audio: np.ndarray,
        sr: int,
        *,
        reduce_noise: bool = True,
        normalize: bool = True,
        target_lufs: float = -23.0,
        trim_silence: bool = True,
    ) -> np.ndarray:
        """
        Full preprocessing pipeline optimized for voice cloning quality.
        Returns cleaned, normalized, silence-trimmed float32 array.
        """
        # 1. Trim leading/trailing silence
        if trim_silence:
            audio, _ = librosa.effects.trim(audio, top_db=30)

        # 2. Noise reduction using spectral gating
        if reduce_noise:
            audio = self._spectral_noise_gate(audio, sr)

        # 3. High-pass filter to remove rumble (<80Hz)
        audio = self._highpass_filter(audio, sr, cutoff=80)

        # 4. Normalize loudness to target LUFS
        if normalize:
            audio = self._loudness_normalize(audio, sr, target_lufs)

        # 5. Clip guard
        audio = np.clip(audio, -1.0, 1.0)

        return audio.astype(np.float32)

    def segment_audio_by_vad(
        self,
        audio: np.ndarray,
        sr: int,
        max_segment_seconds: float = 30.0,
        min_segment_seconds: float = 2.0,
    ) -> list[np.ndarray]:
        """
        Split long audio into speech-only segments using VAD.
        Useful for chunking training data.
        """
        if not HAS_WEBRTCVAD or self._vad is None:
            # Fallback: energy-based segmentation
            return self._energy_based_segmentation(audio, sr, max_segment_seconds, min_segment_seconds)

        frame_samples = int(sr * self.VAD_FRAME_MS / 1000)
        frame_bytes_sr = 16000  # WebRTC VAD always uses 16kHz internally
        # Resample to 16kHz for VAD
        audio_16k = librosa.resample(audio, orig_sr=sr, target_sr=16000)
        frame_16k = int(16000 * self.VAD_FRAME_MS / 1000)

        is_speech = []
        for i in range(0, len(audio_16k) - frame_16k, frame_16k):
            frame_pcm = (audio_16k[i : i + frame_16k] * 32767).astype(np.int16).tobytes()
            try:
                voiced = self._vad.is_speech(frame_pcm, 16000)
            except Exception:
                voiced = True
            is_speech.append(voiced)

        # Build segments from speech frames
        segments: list[np.ndarray] = []
        in_speech = False
        seg_start_orig = 0
        orig_frame = int(sr * self.VAD_FRAME_MS / 1000)

        for i, voiced in enumerate(is_speech):
            t_orig = int(i * orig_frame)
            if voiced and not in_speech:
                in_speech = True
                seg_start_orig = t_orig
            elif not voiced and in_speech:
                in_speech = False
                seg_end_orig = t_orig
                seg = audio[seg_start_orig:seg_end_orig]
                dur = len(seg) / sr
                if min_segment_seconds <= dur <= max_segment_seconds:
                    segments.append(seg)

        # Handle last segment
        if in_speech:
            seg = audio[seg_start_orig:]
            dur = len(seg) / sr
            if dur >= min_segment_seconds:
                if dur > max_segment_seconds:
                    seg_samples = int(max_segment_seconds * sr)
                    for start in range(0, len(seg), seg_samples):
                        chunk = seg[start : start + seg_samples]
                        if len(chunk) / sr >= min_segment_seconds:
                            segments.append(chunk)
                else:
                    segments.append(seg)

        return segments

    def _energy_based_segmentation(
        self, audio: np.ndarray, sr: int,
        max_segment_seconds: float, min_segment_seconds: float
    ) -> list[np.ndarray]:
        """Fallback VAD using energy thresholding when webrtcvad is unavailable."""
        frame_length = int(sr * 0.03)  # 30ms frames
        rms = librosa.feature.rms(y=audio, frame_length=frame_length, hop_length=frame_length)[0]
        threshold = np.max(rms) * 0.05
        is_speech = rms > threshold

        segments: list[np.ndarray] = []
        in_speech = False
        seg_start = 0

        for i, voiced in enumerate(is_speech):
            sample_pos = i * frame_length
            if voiced and not in_speech:
                in_speech = True
                seg_start = sample_pos
            elif not voiced and in_speech:
                in_speech = False
                seg = audio[seg_start:sample_pos]
                dur = len(seg) / sr
                if min_segment_seconds <= dur <= max_segment_seconds:
                    segments.append(seg)

        if in_speech:
            seg = audio[seg_start:]
            dur = len(seg) / sr
            if dur >= min_segment_seconds:
                segments.append(seg[:int(max_segment_seconds * sr)])

        return segments if segments else [audio]

    def save_audio(
        self,
        audio: np.ndarray,
        sr: int,
        output_path: str | Path,
        fmt: str = "wav",
        bit_rate: str = "192k",
    ) -> Path:
        """Save numpy audio to file in specified format."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt in ("wav", "flac"):
            sf.write(str(output_path), audio, sr, subtype="PCM_16")
        elif fmt in ("mp3", "ogg"):
            # Write wav first, convert with ffmpeg
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                sf.write(tmp.name, audio, sr, subtype="PCM_16")
                try:
                    subprocess.run(
                        [
                            "ffmpeg", "-y", "-i", tmp.name,
                            "-codec:a", "libmp3lame" if fmt == "mp3" else "libvorbis",
                            "-b:a", bit_rate,
                            str(output_path),
                        ],
                        capture_output=True,
                        check=True,
                    )
                except FileNotFoundError:
                    # ffmpeg not found — save as wav instead
                    logger.warning("ffmpeg not found — saving as WAV instead of %s", fmt)
                    sf.write(str(output_path.with_suffix('.wav')), audio, sr, subtype="PCM_16")
                    return output_path.with_suffix('.wav')
                finally:
                    Path(tmp.name).unlink(missing_ok=True)
        else:
            sf.write(str(output_path), audio, sr)

        return output_path

    def apply_emotion_prosody(
        self,
        audio: np.ndarray,
        sr: int,
        emotion: str,
        intensity: float = 0.5,
    ) -> np.ndarray:
        """
        Post-process generated audio with emotion-specific prosodic shaping.
        Applied AFTER TTS generation to further enhance emotional coloring.
        intensity: 0.0–1.0
        """
        emotion_params: dict[str, Any] = {
            "happy":          {"speed": 1.08, "pitch": 1.5,  "energy": 1.1},
            "sad":            {"speed": 0.90, "pitch": -2.0, "energy": 0.85},
            "angry":          {"speed": 1.10, "pitch": 2.0,  "energy": 1.25},
            "fearful":        {"speed": 1.15, "pitch": 2.5,  "energy": 1.0},
            "calm":           {"speed": 0.93, "pitch": -1.0, "energy": 0.90},
            "excited":        {"speed": 1.18, "pitch": 3.0,  "energy": 1.20},
            "whispering":     {"speed": 0.88, "pitch": -1.0, "energy": 0.50},
            "narration":      {"speed": 0.95, "pitch": 0.0,  "energy": 1.0},
            "newscast":       {"speed": 1.0,  "pitch": 0.5,  "energy": 1.05},
            "conversational": {"speed": 1.05, "pitch": 0.0,  "energy": 0.95},
        }

        params = emotion_params.get(emotion, {"speed": 1.0, "pitch": 0.0, "energy": 1.0})

        # Apply speed with time-stretching (preserves pitch)
        speed = 1.0 + (params["speed"] - 1.0) * intensity
        if abs(speed - 1.0) > 0.01:
            audio = librosa.effects.time_stretch(audio, rate=speed)

        # Apply pitch shift
        pitch_shift = params["pitch"] * intensity
        if abs(pitch_shift) > 0.1:
            audio = librosa.effects.pitch_shift(audio, sr=sr, n_steps=pitch_shift)

        # Apply energy scaling
        energy = 1.0 + (params["energy"] - 1.0) * intensity
        audio = audio * energy

        return np.clip(audio, -1.0, 1.0).astype(np.float32)

    # ─────────────────────────────────────────────────────────────
    #  Private helpers
    # ─────────────────────────────────────────────────────────────

    def _convert_to_wav(self, path: Path) -> bytes:
        """Use pydub to convert to WAV bytes."""
        seg = AudioSegment.from_file(str(path))
        buf = io.BytesIO()
        seg.export(buf, format="wav")
        buf.seek(0)
        return buf.read()

    def _sha256_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _rms_db(self, audio: np.ndarray) -> float:
        rms = np.sqrt(np.mean(audio ** 2) + 1e-10)
        return float(20 * np.log10(rms))

    def _estimate_snr(self, audio: np.ndarray, sr: int) -> float:
        """
        Estimate SNR by comparing speech segments to non-speech segments.
        Falls back to Parabolic SNR if VAD finds no silence.
        """
        _, intervals = librosa.effects.trim(audio, top_db=20, frame_length=512, hop_length=256)
        if intervals[0] == 0 and intervals[1] == len(audio):
            return 30.0

        signal_part = audio[intervals[0]:intervals[1]]
        noise_parts = np.concatenate([audio[:intervals[0]], audio[intervals[1]:]])

        if len(noise_parts) < 256 or len(signal_part) < 256:
            return 30.0

        signal_rms = np.sqrt(np.mean(signal_part ** 2) + 1e-10)
        noise_rms = np.sqrt(np.mean(noise_parts ** 2) + 1e-10)
        snr = 20 * np.log10(signal_rms / noise_rms + 1e-6)
        return float(np.clip(snr, 0, 60))

    def _vad_analysis(self, audio: np.ndarray, sr: int) -> tuple[int, float]:
        """Returns (speech_frame_count, speech_ratio)."""
        if not HAS_WEBRTCVAD or self._vad is None:
            return self._energy_vad_analysis(audio, sr)

        audio_16k = librosa.resample(audio, orig_sr=sr, target_sr=16000)
        frame_16k = int(16000 * self.VAD_FRAME_MS / 1000)
        total_frames = 0
        speech_frames = 0
        for i in range(0, len(audio_16k) - frame_16k, frame_16k):
            pcm = (audio_16k[i : i + frame_16k] * 32767).astype(np.int16).tobytes()
            total_frames += 1
            try:
                if self._vad.is_speech(pcm, 16000):
                    speech_frames += 1
            except Exception:
                speech_frames += 1
        ratio = speech_frames / total_frames if total_frames > 0 else 0.0
        return speech_frames, ratio

    def _energy_vad_analysis(self, audio: np.ndarray, sr: int) -> tuple[int, float]:
        """Energy-based VAD fallback when webrtcvad is unavailable."""
        frame_length = int(sr * 0.03)
        rms = librosa.feature.rms(y=audio, frame_length=frame_length, hop_length=frame_length)[0]
        threshold = np.max(rms) * 0.05
        speech_frames = int(np.sum(rms > threshold))
        total_frames = len(rms)
        ratio = speech_frames / total_frames if total_frames > 0 else 0.0
        return speech_frames, ratio

    def _estimate_f0(self, audio: np.ndarray, sr: int) -> float | None:
        """Estimate mean fundamental frequency using librosa pyin."""
        try:
            f0, voiced_flag, _ = librosa.pyin(
                audio,
                fmin=librosa.note_to_hz("C2"),
                fmax=librosa.note_to_hz("C7"),
                sr=sr,
            )
            voiced_f0 = f0[voiced_flag]
            if len(voiced_f0) == 0:
                return None
            return float(np.median(voiced_f0))
        except Exception:
            return None

    def _spectral_noise_gate(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Spectral subtraction noise reduction.
        Estimates noise profile from first 0.5s (assumed silence).
        """
        try:
            import noisereduce as nr
            return nr.reduce_noise(y=audio, sr=sr, stationary=False, prop_decrease=0.85)
        except Exception:
            return audio

    def _highpass_filter(self, audio: np.ndarray, sr: int, cutoff: float = 80) -> np.ndarray:
        """Remove low-frequency rumble below cutoff Hz."""
        sos = scipy_signal.butter(4, cutoff, btype="hp", fs=sr, output="sos")
        return scipy_signal.sosfilt(sos, audio).astype(np.float32)

    def _loudness_normalize(
        self, audio: np.ndarray, sr: int, target_lufs: float = -23.0
    ) -> np.ndarray:
        """Simple RMS-based loudness normalization (approximates LUFS)."""
        rms = np.sqrt(np.mean(audio ** 2) + 1e-10)
        target_rms = 10 ** (target_lufs / 20)
        gain = target_rms / rms
        gain = np.clip(gain, 0.01, 100.0)
        return (audio * gain).astype(np.float32)
