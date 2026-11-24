#!/usr/bin/env python3
"""Generate Arabic narration with Microsoft Edge Neural TTS (no API key)."""
from __future__ import annotations

import argparse
import asyncio
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEXT = ROOT / "scripts" / "story.txt"
DEFAULT_OUTPUT = ROOT / "output" / "narration.mp3"
VOICE = "ar-SA-HamedNeural"
MAX_CHARS = 2800


def split_text(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Split only when needed; preserve all user punctuation and wording."""
    text = text.strip()
    if not text:
        raise ValueError("ملف النص فارغ.")
    if limit < 100:
        raise ValueError("--chunk-limit must be at least 100 characters")

    # Prefer natural sentence/paragraph boundaries. No pauses are inserted.
    parts = re.split(r"(?<=[.!؟…؛])\s+|\n+", text)
    chunks: list[str] = []
    current = ""

    def append_piece(piece: str) -> None:
        nonlocal current
        piece = piece.strip()
        if not piece:
            return
        while len(piece) > limit:
            cut = piece.rfind(" ", 0, limit + 1)
            if cut < 1:
                cut = limit
            head, piece = piece[:cut].strip(), piece[cut:].strip()
            if current:
                chunks.append(current)
                current = ""
            if head:
                chunks.append(head)
        candidate = f"{current} {piece}".strip()
        if len(candidate) > limit and current:
            chunks.append(current)
            current = piece
        else:
            current = candidate

    for part in parts:
        append_piece(part)
    if current:
        chunks.append(current)
    return chunks


async def synthesize(chunks: list[str], directory: Path) -> list[Path]:
    outputs: list[Path] = []
    for index, chunk in enumerate(chunks, start=1):
        target = directory / f"part-{index:04d}.mp3"
        print(f"[INFO] Synthesizing part {index}/{len(chunks)} with {VOICE}")
        communicate = edge_tts.Communicate(
            chunk,
            voice=VOICE,
            rate="+0%",
            volume="+0%",
            pitch="+0Hz",
        )
        await communicate.save(str(target))
        if not target.is_file() or target.stat().st_size < 256:
            raise RuntimeError(f"Edge TTS produced an empty/invalid audio part: {index}")
        outputs.append(target)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--chunk-limit", type=int, default=MAX_CHARS)
    args = parser.parse_args()

    if not args.text.is_file():
        raise FileNotFoundError(f"لم يتم العثور على ملف النص: {args.text}")
    text = args.text.read_text(encoding="utf-8")
    chunks = split_text(text, args.chunk_limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to join long narration segments.")

    with tempfile.TemporaryDirectory(prefix="edge-arabic-tts-") as tmp:
        work = Path(tmp)
        parts = asyncio.run(synthesize(chunks, work))
        concat_file = work / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in parts),
            encoding="utf-8",
        )
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", str(concat_file),
             "-c", "copy", str(args.output)],
            check=True,
        )

    if not args.output.is_file() or args.output.stat().st_size < 512:
        raise RuntimeError("Final MP3 was not created correctly.")
    probe = shutil.which("ffprobe")
    if probe:
        result = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(args.output)],
            check=True, capture_output=True, text=True,
        )
        duration = float(result.stdout.strip())
        if duration <= 0:
            raise RuntimeError("Generated audio duration is invalid.")
        print(f"[OK] Duration: {duration:.2f} seconds")
    print(f"[OK] Voice: {VOICE}")
    print(f"[OK] MP3: {args.output} ({args.output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
