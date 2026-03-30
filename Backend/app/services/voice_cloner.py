"""
VoiceCraft Platform — Voice Cloner Service
Uses Coqui XTTS-v2 (Apache 2.0 — completely free and local).
Supports:
  - Zero-shot cloning from ≥6s of reference audio
  - Fine-tuning on 1–5 minutes of audio for superior quality
  - 17+ languages
  - Emotion / speed control
  - Speaker embedding extraction and storage
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

from app.config import get_settings
from app.services.audio_processor import AudioProcessor

logger = logging.getLogger(__name__)
settings = get_settings()


class VoiceClonerService:
    """
    Singleton service wrapping XTTS-v2 with enterprise features.
    Model is loaded once and kept in memory.
    """

    _instance: "VoiceClonerService | None" = None
    _tts: Any = None
    _device: str = "cpu"

    def __new__(cls) -> "VoiceClonerService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self) -> None:
        """Load XTTS-v2 model. Call once at startup."""
        if self._tts is not None:
            return  # already loaded

        logger.info("Loading XTTS-v2 model — this may take 30–60 seconds on first run...")
        from TTS.api import TTS  # lazy import

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("XTTS device: %s", self._device)

        self._tts = TTS(
            model_name=settings.XTTS_MODEL_NAME,
            progress_bar=False,
            gpu=self._device == "cuda",
        )

        # Ensure output dirs exist
        settings.ensure_dirs()
        logger.info("XTTS-v2 model loaded successfully.")

    # ─────────────────────────────────────────────────────────────
    #  Zero-shot cloning (6s+ reference audio)
    # ─────────────────────────────────────────────────────────────

    def clone_and_synthesize(
        self,
        text: str,
        reference_audio_path: str | Path,
        language: str = "en",
        output_path: str | Path | None = None,
        speed: float = 1.0,
        temperature: float = 0.75,
        top_p: float = 0.85,
        top_k: int = 50,
        repetition_penalty: float = 5.0,
        enable_text_splitting: bool = True,
    ) -> tuple[np.ndarray, int]:
        """
        Zero-shot voice cloning synthesis.
        Returns (audio_numpy_float32, sample_rate).

        reference_audio_path: 6s–300s clean speech audio file.
        temperature: 0.5 (stable/consistent) → 1.0 (expressive/variable)
        """
        self._ensure_loaded()

        reference_audio_path = str(reference_audio_path)

        # Preprocess reference audio for quality
        processor = AudioProcessor()
        ref_audio, ref_sr = processor.load_audio(reference_audio_path, target_sr=22050)
        ref_audio = processor.preprocess_for_cloning(ref_audio, ref_sr)

        # Save cleaned reference to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_ref:
            import soundfile as sf
            sf.write(tmp_ref.name, ref_audio, ref_sr)
            clean_ref_path = tmp_ref.name

        try:
            if output_path:
                output_path = str(output_path)
                self._tts.tts_to_file(
                    text=text,
                    speaker_wav=clean_ref_path,
                    language=language,
                    file_path=output_path,
                    speed=speed,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    repetition_penalty=repetition_penalty,
                    enable_text_splitting=enable_text_splitting,
                )
                import soundfile as sf
                audio_out, sr_out = sf.read(output_path)
                return audio_out.astype(np.float32), sr_out
            else:
                audio_out = self._tts.tts(
                    text=text,
                    speaker_wav=clean_ref_path,
                    language=language,
                    speed=speed,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    repetition_penalty=repetition_penalty,
                    enable_text_splitting=enable_text_splitting,
                )
                # XTTS returns list[float] — convert to numpy
                audio_np = np.array(audio_out, dtype=np.float32)
                sample_rate = self._tts.synthesizer.output_sample_rate
                return audio_np, sample_rate
        finally:
            Path(clean_ref_path).unlink(missing_ok=True)

    # ─────────────────────────────────────────────────────────────
    #  Speaker embedding extraction
    # ─────────────────────────────────────────────────────────────

    def extract_speaker_embedding(self, reference_audio_path: str | Path) -> list[float]:
        """
        Extract XTTS speaker embedding from reference audio.
        Embeddings can be stored in DB and reused to skip re-processing.
        Returns a list[float] (512-dim vector).
        """
        self._ensure_loaded()

        processor = AudioProcessor()
        ref_audio, ref_sr = processor.load_audio(reference_audio_path, target_sr=22050)
        ref_audio = processor.preprocess_for_cloning(ref_audio, ref_sr)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            import soundfile as sf
            sf.write(tmp.name, ref_audio, ref_sr)
            tmp_path = tmp.name

        try:
            gpt_cond_latent, speaker_embedding = self._tts.synthesizer.tts_model.get_conditioning_latents(
                audio_path=[tmp_path]
            )
            # Store both latents as a serializable dict
            embedding_dict = {
                "gpt_cond_latent": gpt_cond_latent.cpu().float().numpy().tolist(),
                "speaker_embedding": speaker_embedding.cpu().float().numpy().tolist(),
            }
            return embedding_dict
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def synthesize_from_embedding(
        self,
        text: str,
        embedding_dict: dict,
        language: str = "en",
        speed: float = 1.0,
        temperature: float = 0.75,
        top_p: float = 0.85,
        top_k: int = 50,
    ) -> tuple[np.ndarray, int]:
        """
        Synthesize from stored speaker embedding (no reference audio needed).
        Ultra-fast — avoids re-extracting embedding every time.
        """
        self._ensure_loaded()
        import torch

        gpt_cond_latent = torch.tensor(
            embedding_dict["gpt_cond_latent"], dtype=torch.float
        ).to(self._device)
        speaker_embedding = torch.tensor(
            embedding_dict["speaker_embedding"], dtype=torch.float
        ).to(self._device)

        outputs = self._tts.synthesizer.tts_model.inference(
            text=text,
            language=language,
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            speed=speed,
            enable_text_splitting=True,
        )
        audio_np = np.array(outputs["wav"], dtype=np.float32)
        sample_rate = self._tts.synthesizer.output_sample_rate
        return audio_np, sample_rate

    # ─────────────────────────────────────────────────────────────
    #  Multi-sample reference: merge multiple clips for best quality
    # ─────────────────────────────────────────────────────────────

    def build_composite_reference(
        self,
        audio_paths: list[str | Path],
        output_path: str | Path,
        max_total_seconds: float = 120.0,
    ) -> str:
        """
        Merge multiple reference clips into a single high-quality composite.
        XTTS can use a single long reference for better voice capture.
        Returns path to composite WAV.
        """
        import soundfile as sf

        processor = AudioProcessor()
        segments: list[np.ndarray] = []
        total_dur = 0.0
        silence = np.zeros(int(22050 * 0.3), dtype=np.float32)  # 300ms silence between clips

        for p in audio_paths:
            if total_dur >= max_total_seconds:
                break
            try:
                audio, sr = processor.load_audio(p, target_sr=22050)
                audio = processor.preprocess_for_cloning(audio, sr)
                segs = processor.segment_audio_by_vad(audio, sr)
                for seg in segs:
                    dur = len(seg) / 22050
                    if total_dur + dur > max_total_seconds:
                        remaining = max_total_seconds - total_dur
                        seg = seg[: int(remaining * 22050)]
                    if len(seg) / 22050 >= 1.0:
                        segments.append(seg)
                        segments.append(silence)
                        total_dur += len(seg) / 22050
            except Exception as e:
                logger.warning("Skipping reference audio %s: %s", p, e)

        if not segments:
            raise ValueError("No valid audio segments found in provided files")

        composite = np.concatenate(segments)
        output_path = str(output_path)
        sf.write(output_path, composite, 22050)
        logger.info(
            "Built composite reference: %.1fs from %d files → %s",
            total_dur, len(audio_paths), output_path
        )
        return output_path

    # ─────────────────────────────────────────────────────────────
    #  Fine-tuning (1–5 min of audio → superior quality)
    # ─────────────────────────────────────────────────────────────

    def prepare_fine_tune_dataset(
        self,
        audio_paths: list[str | Path],
        output_dir: str | Path,
        voice_profile_id: str,
    ) -> dict[str, Any]:
        """
        Prepare dataset for fine-tuning XTTS-v2.
        Segments audio, runs Whisper transcription, creates metadata CSV.
        Returns dataset info dict.
        """
        import whisper
        import csv

        output_dir = Path(output_dir)
        wavs_dir = output_dir / "wavs"
        wavs_dir.mkdir(parents=True, exist_ok=True)

        processor = AudioProcessor()
        whisper_model = whisper.load_model(settings.WHISPER_MODEL_SIZE)

        metadata_rows: list[dict] = []
        total_duration = 0.0
        clip_index = 0

        for audio_path in audio_paths:
            try:
                audio, sr = processor.load_audio(audio_path, target_sr=22050)
                audio = processor.preprocess_for_cloning(audio, sr)
                segments = processor.segment_audio_by_vad(
                    audio, sr, max_segment_seconds=15.0, min_segment_seconds=2.0
                )

                for seg in segments:
                    dur = len(seg) / sr
                    if dur < 2.0 or dur > 15.0:
                        continue

                    clip_name = f"{voice_profile_id}_{clip_index:05d}"
                    clip_path = wavs_dir / f"{clip_name}.wav"

                    import soundfile as sf
                    sf.write(str(clip_path), seg, sr)

                    # Whisper transcription
                    result = whisper_model.transcribe(
                        str(clip_path), language=None, fp16=False
                    )
                    text = result["text"].strip()

                    if not text or len(text) < 5:
                        clip_path.unlink(missing_ok=True)
                        continue

                    metadata_rows.append({
                        "audio_file": f"wavs/{clip_name}.wav",
                        "text": text,
                        "speaker_name": voice_profile_id,
                    })
                    total_duration += dur
                    clip_index += 1

            except Exception as e:
                logger.warning("Error processing %s: %s", audio_path, e)

        # Write LJSpeech-format metadata CSV
        metadata_path = output_dir / "metadata.csv"
        with open(metadata_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["audio_file", "text", "speaker_name"])
            writer.writeheader()
            writer.writerows(metadata_rows)

        return {
            "output_dir": str(output_dir),
            "num_clips": clip_index,
            "total_duration_seconds": round(total_duration, 2),
            "metadata_path": str(metadata_path),
        }

    def run_fine_tuning(
        self,
        dataset_dir: str | Path,
        voice_profile_id: str,
        output_model_dir: str | Path,
        num_epochs: int = 5,
        batch_size: int = 8,
        progress_callback=None,
    ) -> str:
        """
        Fine-tune XTTS-v2 on speaker dataset.
        Returns path to fine-tuned model.

        Uses XTTS training API — trains speaker-specific conditioning.
        For 1–3 min of audio: 3–5 epochs produces excellent quality.
        For 3–5 min: 5–10 epochs is optimal.
        """
        self._ensure_loaded()

        from trainer import Trainer, TrainerArgs  # from TTS trainer
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        output_model_dir = Path(output_model_dir)
        output_model_dir.mkdir(parents=True, exist_ok=True)

        # Build training config
        config = XttsConfig()
        config.load_json(
            str(Path(settings.MODELS_DIR) / "xtts_v2" / "config.json")
        )

        config.output_path = str(output_model_dir)
        config.num_epochs = num_epochs
        config.batch_size = batch_size
        config.eval_batch_size = 4
        config.lr = 5e-6
        config.optimizer = "AdamW"
        config.lr_scheduler = "CosineAnnealingLR"
        config.audio.sample_rate = 22050

        # Dataset config
        config.datasets = [{
            "name": "custom",
            "path": str(dataset_dir),
            "meta_file_train": "metadata.csv",
            "language": "en",
            "formatter": "ljspeech",
        }]

        if progress_callback:
            progress_callback(0, num_epochs, "Starting fine-tuning...")

        trainer = Trainer(
            TrainerArgs(restore_path=None, skip_train_epoch=False),
            config,
            output_path=str(output_model_dir),
            model=Xtts.init_from_config(config),
            train_samples=None,
            eval_samples=None,
        )

        trainer.fit()

        if progress_callback:
            progress_callback(num_epochs, num_epochs, "Fine-tuning complete")

        # Return path to best checkpoint
        checkpoints = sorted(output_model_dir.glob("*/best_model*.pth"))
        if checkpoints:
            return str(checkpoints[-1])

        # fallback
        return str(output_model_dir)

    def load_fine_tuned_model(self, model_path: str) -> None:
        """Hot-swap the currently loaded model with a fine-tuned version."""
        self._ensure_loaded()
        logger.info("Loading fine-tuned model from %s", model_path)
        model_dir = Path(model_path).parent
        config_path = model_dir / "config.json"
        if config_path.exists():
            self._tts.synthesizer.tts_model.load_checkpoint(
                self._tts.synthesizer.tts_config,
                checkpoint_path=model_path,
                eval=True,
            )
            logger.info("Fine-tuned model loaded.")
        else:
            raise FileNotFoundError(f"Config not found at {config_path}")

    # ─────────────────────────────────────────────────────────────
    #  Supported languages & capabilities
    # ─────────────────────────────────────────────────────────────

    @property
    def supported_languages(self) -> list[str]:
        return [
            "en", "es", "fr", "de", "it", "pt", "pl", "tr",
            "ru", "nl", "cs", "ar", "zh-cn", "ja", "hu", "ko", "hi",
        ]

    def get_model_info(self) -> dict:
        return {
            "model": "XTTS-v2",
            "provider": "Coqui (Apache 2.0 — Open Source)",
            "languages": self.supported_languages,
            "min_reference_seconds": 6,
            "recommended_reference_seconds": 60,
            "fine_tune_supported": True,
            "device": self._device,
            "loaded": self._tts is not None,
        }

    def _ensure_loaded(self) -> None:
        if self._tts is None:
            self.initialize()


# Singleton accessor
_cloner_instance: VoiceClonerService | None = None


def get_voice_cloner() -> VoiceClonerService:
    global _cloner_instance
    if _cloner_instance is None:
        _cloner_instance = VoiceClonerService()
    return _cloner_instance
