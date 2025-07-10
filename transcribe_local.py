#!/usr/bin/env python3
"""
CLI utility to transcribe a local audio/video file using the existing `transcribe` \
function defined in `lambda_function.py`. The script:

1. Accepts an input media file path as a positional argument.
2. Optionally accepts an output text file path; if omitted, it will derive one
   from the input file name with a `.txt` extension.
3. Detects the MIME type of the input file for more accurate transcription.
4. Reads the file content, invokes `transcribe`, and writes the resulting text
   to the output file.

Environment variables expected:
- SONIOX_TOKEN : Your Soniox API token.
"""

import argparse
import logging
import mimetypes
import sys
from pathlib import Path

from lambda_function import transcribe  # type: ignore

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def detect_mime_type(file_path: Path) -> str:
    """Return the best-guess MIME type for the given file path."""
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcribe a local audio/video file using Soniox STT service "
        "and save the transcript to a text file."
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to the local audio, voice, or video file to be transcribed.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Path to the output text file (defaults to <input_file>.txt)",
    )

    args = parser.parse_args()
    input_path: Path = args.input_file.expanduser().resolve()

    if not input_path.exists() or not input_path.is_file():
        logger.error(
            "Input file '%s' does not exist or is not a regular file.", input_path
        )
        sys.exit(1)

    output_path: Path
    if args.output:
        output_path = args.output.expanduser().resolve()
    else:
        output_path = input_path.with_suffix(".txt")

    # Detect MIME type for Soniox
    mime_type = detect_mime_type(input_path)
    logger.info("Detected MIME type: %s", mime_type)

    # Read file content
    try:
        file_bytes = input_path.read_bytes()
    except Exception as e:
        logger.error("Failed to read input file: %s", e)
        sys.exit(1)

    logger.info("Starting transcription for '%s'…", input_path.name)
    result = transcribe(file_bytes, mime_type)

    # `transcribe` returns either "Transcription: <text>" or an error message.
    if result.startswith("Transcription:"):
        transcript_text = result[len("Transcription:") :].lstrip()
        try:
            output_path.write_text(transcript_text, encoding="utf-8")
            logger.info("Transcript written to '%s'", output_path)
        except Exception as e:
            logger.error("Failed to write transcript file: %s", e)
            sys.exit(1)
    else:
        logger.error("Transcription failed: %s", result)
        sys.exit(1)


if __name__ == "__main__":
    main()
