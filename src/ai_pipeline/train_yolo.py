import os
from roboflow import Roboflow
from ultralytics import YOLO

# 1. Download a verified public contraband dataset from Roboflow Universe
rf = Roboflow(api_key="1S38B9yTcgpIKbG51dPl")
import os
from roboflow import Roboflow
from ultralytics import YOLO

# 1. Initialize Roboflow with your API key
rf = Roboflow(api_key="1S38B9yTcgpIKbG51dPl")

# Use version 1 (universally available on public Roboflow projects):
project = rf.workspace("cbait").project("new-drugs")
dataset = project.version(2).download("yolov8")

# 2. Base model setup
model = YOLO("yolov8n.pt")

# 3. Train on downloaded dataset
results = model.train(
    data=f"{dataset.location}/data.yaml",
    epochs=3,              # 3 epochs is sufficient to verify custom weight convergence
    imgsz=320,             # Halving image dimension speeds up CPU matrix math by ~4x
    batch=16,
    device="cpu",
    project="models",
    name="drugshield_contraband"
)

print("\n" + "=" * 60)
print("TRAINING COMPLETE!")
print(f"Weights saved to: {results.save_dir}/weights/best.pt")
print("=" * 60)
# 2. Initialize the YOLOv8 Nano base model
model = YOLO("yolov8n.pt")

# 3. Train on the downloaded dataset
results = model.train(
    data=f"{dataset.location}/data.yaml",
    epochs=15,             # 15 epochs provides a working demo without excessive training time
    imgsz=640,
    batch=8,
    device="cpu",          # Runs on CPU; change to device=0 if you have an NVIDIA GPU
    project="src/ai_pipeline/models",
    name="drugshield_contraband"
)

print("\n" + "=" * 60)
print("TRAINING FINISHED!")
print("Weights saved to: src/ai_pipeline/models/drugshield_contraband/weights/best.pt")
print("=" * 60)