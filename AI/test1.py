import torch
import whisper

device = "cuda" if torch.cuda.is_available() else "cpu"
model = whisper.load_model("turbo").to(device)

result = model.transcribe("udp_uploads/combined_audio.mp3")
print(result["text"])
