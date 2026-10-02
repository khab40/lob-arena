"""Small causal classifier. Execute only inside an authorized Nebius GPU Job."""
import math

import torch
from torch import nn


class CausalBlock(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.norm1, self.norm2 = nn.LayerNorm(width), nn.LayerNorm(width)
        self.attention = nn.MultiheadAttention(width, 4, dropout=0.1, batch_first=True)
        self.dropout = nn.Dropout(0.1)
        self.ffn = nn.Sequential(nn.Linear(width, 4 * width), nn.GELU(), nn.Dropout(0.1),
                                 nn.Linear(4 * width, width), nn.Dropout(0.1))

    def forward(self, x, blocked, valid):
        normalized = self.norm1(x)
        attention, _ = self.attention(normalized, normalized, normalized,
                                      attn_mask=blocked, need_weights=False)
        x = (x + self.dropout(attention)).masked_fill(~valid[..., None], 0)
        return (x + self.ffn(self.norm2(x))).masked_fill(~valid[..., None], 0)


class SequenceClassifier(nn.Module):
    def __init__(self, width):
        super().__init__()
        if width not in (64, 128):
            raise ValueError("fixed-grid width required")
        self.projection = nn.Linear(120, width)
        self.blocks = nn.ModuleList([CausalBlock(width) for _ in range(2)])
        self.norm, self.head = nn.LayerNorm(width), nn.Linear(width, 1)
        position = torch.arange(64, dtype=torch.float32)[:, None]
        frequency = torch.exp(torch.arange(0, width, 2, dtype=torch.float32) * (-math.log(10000.0) / width))
        encoding = torch.zeros(64, width)
        encoding[:, 0::2], encoding[:, 1::2] = torch.sin(position * frequency), torch.cos(position * frequency)
        self.register_buffer("encoding", encoding, persistent=True)

    def encode(self, values, valid, missing):
        if (values.ndim != 3 or tuple(values.shape[1:]) != (64, 60)
                or valid.shape != values.shape[:2] or missing.shape != values.shape
                or valid.dtype != torch.bool or missing.dtype != torch.bool
                or values.dtype != torch.float32):
            raise ValueError("expected float32 values and Boolean masks for 64 by 60 inputs")
        if not torch.isfinite(values).all() or not valid.any(dim=1).all():
            raise ValueError("nonfinite or all-padding window")
        if (missing & ~valid[..., None]).any():
            raise ValueError("missingness indicators on padding")
        features = torch.cat((values.masked_fill(missing | ~valid[..., None], 0), missing.float()), dim=-1)
        x = (self.projection(features) + self.encoding).masked_fill(~valid[..., None], 0)
        causal = torch.ones(64, 64, dtype=torch.bool, device=values.device).tril()
        allowed = causal[None] & valid[:, :, None] & valid[:, None, :]
        # Give discarded padded queries one finite key; valid queries never see it.
        allowed |= ~valid[:, :, None] & torch.eye(64, dtype=torch.bool, device=values.device)[None]
        blocked = (~allowed).repeat_interleave(4, dim=0)  # PyTorch True means blocked.
        for block in self.blocks:
            x = block(x, blocked, valid)
        return self.norm(x).masked_fill(~valid[..., None], 0)

    def forward(self, values, valid, missing):
        x = self.encode(values, valid, missing)
        last = torch.arange(64, device=values.device)[None].expand_as(valid).masked_fill(~valid, -1).max(dim=1).values
        logits = self.head(x[torch.arange(len(x), device=x.device), last]).squeeze(-1)
        if not torch.isfinite(logits).all():
            raise ValueError("nonfinite model output")
        return logits
