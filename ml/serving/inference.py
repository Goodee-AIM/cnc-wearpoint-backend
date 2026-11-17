"""Run record-level inference from an Epoch 10 PyTorch checkpoint."""
import argparse
import json

import torch
from torch import nn
from torchvision.models import resnet18

from preprocessing import preprocess_image, preprocess_sensor


class ImageForceYFusionModel(nn.Module):
    def __init__(self, embedding_dim):
        super().__init__()
        self.image_encoder = resnet18(weights=None)
        self.image_encoder.fc = nn.Identity()
        self.fy_encoder = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=7, padding=3),
            nn.BatchNorm1d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(2),
            nn.Conv1d(32, 64, kernel_size=5, padding=2),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(2),
            nn.Conv1d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm1d(128),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool1d(1),
        )
        self.fusion_embedding = nn.Sequential(
            nn.Linear(640, embedding_dim), nn.BatchNorm1d(embedding_dim),
            nn.ReLU(), nn.Dropout(0.3),
        )
        self.regressor = nn.Sequential(
            nn.Linear(embedding_dim, 128), nn.ReLU(),
            nn.Dropout(0.3), nn.Linear(128, 1),
        )
        self.classifier = nn.Sequential(
            nn.Linear(embedding_dim, 128), nn.ReLU(),
            nn.Dropout(0.3), nn.Linear(128, 1),
        )

    def forward(self, image, sensor):
        features = torch.cat(
            (self.image_encoder(image), self.fy_encoder(sensor).flatten(1)), dim=1
        )
        embedding = self.fusion_embedding(features)
        return self.regressor(embedding), self.classifier(embedding)


def load_model(checkpoint_path, device):
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if int(checkpoint["epoch"]) != 10:
        raise ValueError("Expected an Epoch 10 checkpoint.")
    model = ImageForceYFusionModel(int(checkpoint["fusion_embed_dim"]))
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    return model.to(device).eval(), checkpoint


@torch.inference_mode()
def predict_record(
    model,
    checkpoint,
    image_path,
    sensor_path,
    crop,
    batch_size=32,
):
    if batch_size < 1:
        raise ValueError(
            "batch_size must be positive."
        )

    device = next(model.parameters()).device

    image = preprocess_image(
        image_path,
        crop,
        checkpoint,
    ).to(device)

    windows, (start, end), fs_hz = preprocess_sensor(
        sensor_path,
        checkpoint,
    )

    # 요청당 이미지는 한 장이므로
    # ResNet18 이미지 특징을 한 번만 계산해서 재사용합니다.
    image_feature = model.image_encoder(
        image.unsqueeze(0)
    )

    wear_sum = 0.0
    probability_sum = 0.0

    for batch in windows.split(batch_size):
        batch = batch.to(device)

        # Sensor window만 batch 단위로 인코딩합니다.
        sensor_feature = model.fy_encoder(
            batch
        ).flatten(1)

        # 동일한 이미지 특징을 현재 batch 크기만큼 재사용합니다.
        image_features = image_feature.expand(
            len(batch),
            -1,
        )

        features = torch.cat(
            (
                image_features,
                sensor_feature,
            ),
            dim=1,
        )

        embedding = model.fusion_embedding(
            features
        )

        wear = model.regressor(
            embedding
        )

        logits = model.classifier(
            embedding
        )

        wear_sum += (
            wear.double().sum().item()
        )

        probability_sum += (
            logits.sigmoid()
            .double()
            .sum()
            .item()
        )

    probability = (
        probability_sum / len(windows)
    )

    threshold = float(
        checkpoint["cls_threshold"]
    )

    return {
        "epoch": int(
            checkpoint["epoch"]
        ),
        "predicted_wear_um": (
            wear_sum / len(windows)
        ),
        "flank_wear_probability": (
            probability
        ),
        "predicted_type": (
            "flank_wear"
            if probability >= threshold
            else "other_wear"
        ),
        "threshold": threshold,
        "window_count": len(windows),
        "sampling_hz": fs_hz,
        "cut_start_index": start,
        "cut_end_index_exclusive": end,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--image", required=True, help="Paired original RGB image")
    parser.add_argument("--sensor-csv", required=True)
    parser.add_argument("--crop", type=int, nargs=4, required=True,
                        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    model, checkpoint = load_model(args.checkpoint, args.device)
    result = predict_record(
        model, checkpoint, args.image, args.sensor_csv, args.crop, args.batch_size
    )
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
