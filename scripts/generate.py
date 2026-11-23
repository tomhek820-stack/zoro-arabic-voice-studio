#!/usr/bin/env python3
"""Generate Arabic narration with Chatterbox Multilingual V3."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import torch
import torchaudio
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEXT = ROOT / "scripts" / "story.txt"
DEFAULT_OUTPUT = ROOT / "output" / "narration.wav"
DEFAULT_REFERENCE = ROOT / "assets" / "male_reference.wav"


def split_text(text: str, limit: int = 230) -> list[str]:
    """Split on sentence boundaries, then words; preserve all source text."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        raise ValueError("ملف النص فارغ.")
    sentences = re.split(r"(?<=[.!؟…])\s+|\n+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > limit:
            words = sentence.split()
            for word in words:
                candidate = f"{current} {word}".strip()
                if len(candidate) > limit and current:
                    chunks.append(current)
                    current = word
                else:
                    current = candidate
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) > limit and current:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--exaggeration", type=float, default=0.68)
    parser.add_argument("--cfg-weight", type=float, default=0.35)
    parser.add_argument("--chunk-limit", type=int, default=230)
    args = parser.parse_args()

    if not args.text.is_file():
        raise FileNotFoundError(f"لم يتم العثور على ملف النص: {args.text}")
    text = args.text.read_text(encoding="utf-8").strip()
    chunks = split_text(text, args.chunk_limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] Device: {device}")
    print(f"[INFO] Text chunks: {len(chunks)}")
    print("[INFO] Loading Chatterbox Multilingual V3...")
    # The published chatterbox-tts 0.1.7 API accepts the device only.
    # Multilingual TTS is already selected by this class; no t3_model argument.
    model = ChatterboxMultilingualTTS.from_pretrained(device=device)

    use_reference = args.reference.is_file()
    if use_reference:
        print(f"[INFO] Using licensed male reference voice: {args.reference.name}")
    else:
        print("[WARN] No male reference clip found; using the model's default speaker.")
        print("[WARN] Add assets/male_reference.wav to condition the output on a male voice.")

    gap = torch.zeros((1, int(model.sr * 0.28)), dtype=torch.float32)
    rendered = []
    for index, chunk in enumerate(chunks, start=1):
        print(f"[INFO] Generating chunk {index}/{len(chunks)}")
        kwargs = {
            "language_id": "ar",
            "exaggeration": args.exaggeration,
            "cfg_weight": args.cfg_weight,
        }
        if use_reference:
            kwargs["audio_prompt_path"] = str(args.reference)
        with torch.inference_mode():
            wav = model.generate(chunk, **kwargs)
        if wav.ndim == 1:
            wav = wav.unsqueeze(0)
        wav = wav.detach().cpu().float()
        rendered.append(wav)
        if index != len(chunks):
            rendered.append(gap)

    audio = torch.cat(rendered, dim=-1)
    # Peak normalization with headroom; do not aggressively compress dynamics.
    peak = audio.abs().max().item()
    if peak > 0:
        audio = audio * (0.92 / peak)

    torchaudio.save(str(args.output), audio, model.sr)
    print(f"[OK] WAV saved: {args.output} ({model.sr} Hz)")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        mp3_path = args.output.with_suffix(".mp3")
        subprocess.run(
            [ffmpeg, "-y", "-i", str(args.output), "-codec:a", "libmp3lame",
             "-b:a", "192k", str(mp3_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        print(f"[OK] MP3 saved: {mp3_path}")
    else:
        print("[WARN] ffmpeg missing; WAV is ready, MP3 conversion skipped.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
