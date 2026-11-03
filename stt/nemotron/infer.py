#!/usr/bin/env python3
"""Nemotron 3.5 ASR Streaming inference script."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_nv_one_logger

import torch
import soundfile as sf
import numpy as np
from nemo.collections.asr.models import EncDecRNNTBPEModel


@torch.no_grad()
def transcribe_file(model, audio_path, target_lang="en-US", device="cuda"):
    """Transcribe a single audio file using direct inference."""
    # Read audio
    data, sr = sf.read(audio_path)
    if sr != 16000:
        import librosa
        data = librosa.resample(data, orig_sr=sr, target_sr=16000)
        sr = 16000
    if data.ndim > 1:
        data = data.mean(axis=1)
    
    # Convert to torch tensor
    audio = torch.tensor(data, dtype=torch.float32, device=device).unsqueeze(0)
    audio_len = torch.tensor([audio.shape[1]], device=device)
    
    # Preprocess (Mel spectrogram)
    processed, processed_len = model.preprocessor(input_signal=audio, length=audio_len)
    
    # Set inference prompt
    model.set_inference_prompt(target_lang)
    
    # Encode
    encoded, encoded_len = model.encoder(audio_signal=processed, length=processed_len)
    
    # Apply prompt to encoded output
    encoded = model._apply_prompt_to_encoded(encoded)
    
    # Decode with RNNT greedy decoding
    with torch.no_grad():
        hypotheses = model.decoding.rnnt_decoder_predictions_tensor(
            encoded, encoded_len, return_hypotheses=False
        )
    
    if isinstance(hypotheses, (list, tuple)):
        hyp = hypotheses[0]
    else:
        hyp = hypotheses
    
    if hasattr(hyp, 'text'):
        return hyp.text
    elif isinstance(hyp, (list, tuple)):
        return hyp[0]
    return str(hyp)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Nemotron 3.5 ASR Streaming")
    parser.add_argument("audio_path", help="Path to WAV file (16kHz mono)")
    parser.add_argument("--lang", default="en-US",
                        help="Target language (e.g. en-US, es-ES, de-DE, ru-RU, auto)")
    parser.add_argument("--device", default="cuda", help="Device: cuda or cpu")
    args = parser.parse_args()
    
    print(f"Loading model...")
    model = EncDecRNNTBPEModel.from_pretrained(
        "nvidia/nemotron-3.5-asr-streaming-0.6b"
    )
    model = model.to(args.device)
    model.eval()
    print(f"Model loaded on {args.device}")
    
    text = transcribe_file(model, args.audio_path, args.lang, args.device)
    print(f"\n=== Transcription ===")
    print(text)


if __name__ == "__main__":
    main()
