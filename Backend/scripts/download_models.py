#!/usr/bin/env python3
"""
VoiceCraft Platform — Model Downloader
Downloads all required ML model weights:
  - XTTS-v2 voice cloning model (Coqui, Apache 2.0)
  - Whisper speech recognition (OpenAI, MIT)
  - AASIST deepfake detection (HuggingFace Hub, free)
  - RawNet2 weights (optional, from research checkpoints)

Run once before starting the platform:
  python scripts/download_models.py
"""
import os
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODELS_DIR = Path(os.getenv("MODELS_DIR", "./models_cache"))
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def download_xtts_v2():
    logger.info("Downloading XTTS-v2 voice cloning model (Coqui, Apache 2.0)...")
    try:
        from TTS.api import TTS
        # This triggers download of XTTS-v2 (~1.8GB) on first call
        tts = TTS(
            model_name="tts_models/multilingual/multi-dataset/xtts_v2",
            progress_bar=True,
            gpu=False,
        )
        logger.info("✅ XTTS-v2 downloaded successfully")
    except Exception as e:
        logger.error("❌ XTTS-v2 download failed: %s", e)
        logger.info("Manual install: pip install TTS && tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 --list_models")


def download_whisper():
    logger.info("Downloading Whisper speech recognition (OpenAI, MIT License)...")
    try:
        import whisper
        for size in ["base", "small"]:
            logger.info("  Downloading Whisper %s...", size)
            whisper.load_model(size, download_root=str(MODELS_DIR / "whisper"))
        logger.info("✅ Whisper models downloaded")
    except Exception as e:
        logger.error("❌ Whisper download failed: %s", e)


def download_aasist():
    logger.info("Downloading AASIST deepfake detection (HuggingFace Hub, free)...")
    try:
        from transformers import AutoModelForAudioClassification, AutoFeatureExtractor
        cache_dir = str(MODELS_DIR / "aasist")

        # Try primary model
        models_to_try = [
            "hf-audio/aasist-conformer",
            "Pang-Nyan/aasist-add-conformer",
        ]
        for model_name in models_to_try:
            try:
                AutoFeatureExtractor.from_pretrained(model_name, cache_dir=cache_dir)
                AutoModelForAudioClassification.from_pretrained(model_name, cache_dir=cache_dir)
                logger.info("✅ AASIST downloaded from %s", model_name)
                break
            except Exception as e:
                logger.warning("  %s failed: %s", model_name, e)
                continue
    except Exception as e:
        logger.error("❌ AASIST download failed: %s", e)
        logger.info("Detection will fall back to RawNet2 + classical features.")


def download_speechbrain():
    logger.info("Downloading SpeechBrain speaker verification (MIT License)...")
    try:
        from speechbrain.inference.speaker import EncoderClassifier
        savedir = str(MODELS_DIR / "speechbrain_ecapa")
        _ = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=savedir,
        )
        logger.info("✅ SpeechBrain ECAPA-TDNN downloaded")
    except Exception as e:
        logger.error("❌ SpeechBrain download failed: %s", e)


def verify_ffmpeg():
    import subprocess
    logger.info("Checking ffmpeg...")
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        version = result.stdout.split("\n")[0]
        logger.info("✅ ffmpeg found: %s", version)
    except FileNotFoundError:
        logger.error("❌ ffmpeg not found! Install: sudo apt-get install ffmpeg")
        sys.exit(1)


def verify_espeak():
    import subprocess
    logger.info("Checking espeak-ng (required for XTTS text processing)...")
    try:
        subprocess.run(["espeak-ng", "--version"], capture_output=True, check=True)
        logger.info("✅ espeak-ng found")
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.warning("⚠️  espeak-ng not found. Install: sudo apt-get install espeak-ng")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("VoiceCraft Platform — Model Download Script")
    logger.info("Models will be saved to: %s", MODELS_DIR.absolute())
    logger.info("=" * 60)

    # System checks
    verify_ffmpeg()
    verify_espeak()

    # Download models
    download_xtts_v2()
    download_whisper()
    download_aasist()
    download_speechbrain()

    logger.info("=" * 60)
    logger.info("Download complete. You can now start VoiceCraft Platform:")
    logger.info("  docker-compose up --build")
    logger.info("  OR: uvicorn app.main:app --reload")
    logger.info("=" * 60)
