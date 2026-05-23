#!/usr/bin/env python3
"""
深度学习模型训练框架
===================
金融 AI 研究的模型训练流水线，支持多种模型架构。

功能：
- PyTorch 训练循环（支持早停、学习率调度、梯度裁剪）
- 金融数据集加载（时间序列、文本分类、文档理解）
- 常用金融模型：Transformer、BERT、LSTM、随机森林
- 实验追踪（wandb / tensorboard）
"""

import os
import sys
import json
import random
import warnings
from pathlib import Path
from typing import Optional, Callable

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW, SGD
from torch.optim.lr_scheduler import CosineAnnealingLR, ReduceLROnPlateau

warnings.filterwarnings("ignore")


# ─── 随机种子 ────────────────────────────────────────────

def set_seed(seed: int = 42):
    """固定所有随机种子，确保实验可复现。"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    print(f"[Seed] 随机种子已固定为 {seed}")


# ─── 设备管理 ────────────────────────────────────────────

def get_device() -> torch.device:
    """自动选择 GPU/CPU 设备。"""
    if torch.cuda.is_available():
        device = torch.device("cuda")
        print(f"[Device] 使用 GPU: {torch.cuda.get_device_name(0)}")
        print(f"[Device] GPU 内存: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
        print("[Device] 使用 Apple Silicon GPU")
    else:
        device = torch.device("cpu")
        print("[Device] 使用 CPU")
    return device


# ─── 数据集模板 ──────────────────────────────────────────

class FinancialTimeSeriesDataset(Dataset):
    """金融时序数据集。"""

    def __init__(self, data: np.ndarray, seq_len: int = 60, horizon: int = 1):
        self.X, self.y = [], []
        for i in range(len(data) - seq_len - horizon + 1):
            self.X.append(data[i:i+seq_len])
            self.y.append(data[i+seq_len:i+seq_len+horizon])
        self.X = torch.FloatTensor(np.array(self.X))
        self.y = torch.FloatTensor(np.array(self.y))

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


class TextClassificationDataset(Dataset):
    """文本分类数据集（用于金融新闻分类、情感分析）。"""

    def __init__(self, texts: list, labels: list, tokenizer, max_len: int = 512):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        encoding = self.tokenizer(
            self.texts[idx],
            max_length=self.max_len,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )
        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": torch.tensor(self.labels[idx], dtype=torch.long)
        }


# ─── 训练器 ──────────────────────────────────────────────

class Trainer:
    """通用训练器。"""

    def __init__(
        self,
        model: nn.Module,
        train_loader: DataLoader,
        val_loader: Optional[DataLoader],
        optimizer: torch.optim.Optimizer,
        scheduler: Optional[object],
        criterion: nn.Module,
        device: torch.device,
        early_stopping_patience: int = 10,
        gradient_clip_value: float = 1.0,
        experiment_name: str = "experiment",
        use_wandb: bool = False,
    ):
        self.model = model.to(device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.optimizer = optimizer
        self.scheduler = scheduler
        self.criterion = criterion
        self.device = device
        self.patience = early_stopping_patience
        self.gradient_clip_value = gradient_clip_value
        self.experiment_name = experiment_name
        self.use_wandb = use_wandb

        self.best_val_loss = float("inf")
        self.epochs_without_improvement = 0
        self.history = {"train_loss": [], "val_loss": [], "train_metric": [], "val_metric": []}

        if use_wandb:
            try:
                import wandb
                wandb.init(name=experiment_name, config=model.config if hasattr(model, "config") else {})
                self.wandb = wandb
                print("[WandB] 已启用实验追踪")
            except ImportError:
                print("[WandB] 未安装，跳过实验追踪")

    def train_epoch(self) -> tuple[float, float]:
        self.model.train()
        total_loss = 0
        for batch in self.train_loader:
            batch = {k: v.to(self.device) for k, v in batch.items()}

            self.optimizer.zero_grad()
            outputs = self.model(**batch)
            loss = outputs.loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.gradient_clip_value)
            self.optimizer.step()

            total_loss += loss.item()

        avg_loss = total_loss / len(self.train_loader)
        return avg_loss, 0.0

    @torch.no_grad()
    def evaluate(self) -> tuple[float, float]:
        self.model.eval()
        total_loss = 0
        correct = 0
        total = 0

        for batch in self.val_loader:
            batch = {k: v.to(self.device) for k, v in batch.items()}
            outputs = self.model(**batch)
            loss = self.criterion(outputs.logits, batch["labels"])

            total_loss += loss.item()
            preds = outputs.logits.argmax(dim=-1)
            correct += (preds == batch["labels"]).sum().item()
            total += batch["labels"].size(0)

        avg_loss = total_loss / len(self.val_loader)
        accuracy = correct / total if total > 0 else 0
        return avg_loss, accuracy

    def fit(self, epochs: int):
        """运行完整训练流程。"""
        for epoch in range(epochs):
            train_loss, train_metric = self.train_epoch()
            val_loss, val_metric = 0.0, 0.0

            if self.val_loader:
                val_loss, val_metric = self.evaluate()

            if self.scheduler:
                if isinstance(self.scheduler, ReduceLROnPlateau):
                    self.scheduler.step(val_loss)
                else:
                    self.scheduler.step()

            self.history["train_loss"].append(train_loss)
            self.history["val_loss"].append(val_loss)
            self.history["train_metric"].append(train_metric)
            self.history["val_metric"].append(val_metric)

            print(
                f"[Epoch {epoch+1:03d}/{epochs}] "
                f"train_loss: {train_loss:.4f} | val_loss: {val_loss:.4f} | "
                f"val_acc: {val_metric:.4f}"
            )

            if self.use_wandb and hasattr(self, "wandb"):
                self.wandb.log({
                    "train_loss": train_loss,
                    "val_loss": val_loss,
                    "val_accuracy": val_metric,
                    "epoch": epoch + 1,
                })

            if val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                self.epochs_without_improvement = 0
                self.save_checkpoint("best_model.pt")
                print(f"  ↳ 新的最优模型已保存 (val_loss={val_loss:.4f})")
            else:
                self.epochs_without_improvement += 1
                if self.epochs_without_improvement >= self.patience:
                    print(f"[EarlyStopping] 在第 {epoch+1} 轮触发早停")
                    break

        print(f"[完成] 训练完成，最优验证损失: {self.best_val_loss:.4f}")
        return self.history

    def save_checkpoint(self, path: str):
        torch.save({
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "best_val_loss": self.best_val_loss,
            "history": self.history,
        }, path)

    def load_checkpoint(self, path: str):
        checkpoint = torch.load(path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.best_val_loss = checkpoint["best_val_loss"]
        print(f"[加载] 从 {path} 加载模型 (val_loss={self.best_val_loss:.4f})")


# ─── 常用模型定义 ────────────────────────────────────────

class FinancialLSTM(nn.Module):
    """用于金融时序预测的 LSTM。"""

    def __init__(self, input_size: int, hidden_size: int, num_layers: int, output_size: int, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=dropout)
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size // 2, output_size)
        )

    def forward(self, x):
        _, (h_n, _) = self.lstm(x)
        out = self.fc(h_n[-1])
        return out


class TransformerClassifier(nn.Module):
    """基于 Transformer 的文本分类模型（用于金融文档理解）。"""

    def __init__(self, vocab_size: int, embed_dim: int, num_heads: int, num_layers: int, num_classes: int, dropout: float = 0.1):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.pos_encoding = PositionalEncoding(embed_dim, dropout)
        encoder_layer = nn.TransformerEncoderLayer(d_model=embed_dim, nhead=num_heads, dropout=dropout, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers)
        self.fc = nn.Linear(embed_dim, num_classes)

    def forward(self, input_ids, attention_mask=None):
        x = self.embedding(input_ids)
        x = self.pos_encoding(x)
        x = self.transformer(x)
        x = x.mean(dim=1)
        return self.fc(x)


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 5000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)

    def forward(self, x):
        x = x + self.pe[:, : x.size(1), :]
        return self.dropout(x)


# ─── 演示 ────────────────────────────────────────────────

if __name__ == "__main__":
    set_seed(42)
    device = get_device()

    dummy_data = np.random.randn(1000, 5).astype(np.float32)
    train_dataset = FinancialTimeSeriesDataset(dummy_data[:800], seq_len=60)
    val_dataset = FinancialTimeSeriesDataset(dummy_data[800:], seq_len=60)

    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=32)

    model = FinancialLSTM(input_size=5, hidden_size=64, num_layers=2, output_size=1)
    optimizer = AdamW(model.parameters(), lr=1e-3)
    scheduler = CosineAnnealingLR(optimizer, T_max=50)
    criterion = nn.MSELoss()

    trainer = Trainer(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        optimizer=optimizer,
        scheduler=scheduler,
        criterion=criterion,
        device=device,
        early_stopping_patience=10,
        experiment_name="financial_lstm_demo",
    )

    history = trainer.fit(epochs=10)
    trainer.save_checkpoint("lstm_finance_demo.pt")
