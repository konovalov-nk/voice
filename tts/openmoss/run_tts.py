import torch
import sys
sys.path.insert(0, "./MOSS-TTS-Nano-100M")
from transformers import AutoModel
import soundfile as sf
import numpy as np

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")

model_path = "./MOSS-TTS-Nano-100M"

model = AutoModel.from_pretrained(
    model_path,
    trust_remote_code=True,
    torch_dtype=torch.float16,
    device_map=device,
    attn_implementation="sdpa"
)
model.eval()

# Генерируем аудио с референсом
output_path = "output.wav"
model.inference(
    text="Hello, this is a test of the MOSS TTS model.",
    output_audio_path=output_path,
    prompt_audio_path="reference.mp3",
    mode="voice_clone",
    max_new_frames=300,
    do_sample=True,
    text_temperature=1.5,
    audio_temperature=1.7,
)

print(f"Audio saved to {output_path}")
