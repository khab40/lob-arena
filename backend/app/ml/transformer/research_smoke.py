"""GPU-only behavior checks invoked by the reviewed Nebius smoke Job wrapper."""
from pathlib import Path

import torch

from .research_checkpoint import load_checkpoint, write_checkpoint
from .research_model import SequenceClassifier
from .research_policy import Trial
from .research_training import configure


def run_smoke(output: Path, *, bindings, publish):
    configure(42)  # Reject local CPU execution before constructing any model.
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for width in (64, 128):
        trial = Trial(width, 0.0003)
        model = SequenceClassifier(width).to("cuda").eval()
        values = torch.randn(2, 64, 60, device="cuda")
        valid = torch.ones(2, 64, dtype=torch.bool, device="cuda")
        valid[0, :16] = False
        missing = torch.zeros_like(values, dtype=torch.bool)
        missing[1, 33, 5] = True
        with torch.inference_mode():
            original = model(values, valid, missing)
            encoded = model.encode(values, valid, missing)
            changed = values.clone()
            changed[:, 32:] += 100
            causal = model.encode(changed, valid, missing)
            torch.testing.assert_close(encoded[:, :32], causal[:, :32], atol=1e-6, rtol=0)
            changed = values.clone()
            changed[0, :16] = 12345
            changed[1, 33, 5] = -12345
            torch.testing.assert_close(original, model(changed, valid, missing), atol=1e-6, rtol=0)
            individual = torch.cat([model(values[i:i+1], valid[i:i+1], missing[i:i+1]) for i in range(2)])
            torch.testing.assert_close(original, individual, atol=1e-6, rtol=0)
            try:
                model(values, torch.zeros_like(valid), missing & False)
            except ValueError:
                pass
            else:
                raise AssertionError("all-padding window accepted")
        optimizer = torch.optim.AdamW(model.parameters(), lr=trial.learning_rate, weight_decay=0.01)
        def step(target, opt):
            target.train()
            opt.zero_grad(set_to_none=True)
            logits = target(values, valid, missing)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, torch.tensor([0., 1.], device="cuda"))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(target.parameters(), 1.0, error_if_nonfinite=True)
            opt.step()
            return logits.detach()
        step(model, optimizer)
        folder = output / str(width)
        folder.mkdir()
        receipt = write_checkpoint(folder, model=model, optimizer=optimizer, trial=trial,
            bindings=bindings, progress={"epoch": 1, "global_step": 1}, publish=publish)
        expected_logits = step(model, optimizer)
        resumed = SequenceClassifier(width).to("cuda")
        resumed_optimizer = torch.optim.AdamW(resumed.parameters(), lr=trial.learning_rate, weight_decay=0.01)
        load_checkpoint(folder / receipt["name"], receipt["sha256"], model=resumed,
                        optimizer=resumed_optimizer, trial=trial, bindings=bindings)
        actual_logits = step(resumed, resumed_optimizer)
        torch.testing.assert_close(expected_logits, actual_logits, atol=1e-6, rtol=0)
        for name, parameter in model.state_dict().items():
            torch.testing.assert_close(parameter, resumed.state_dict()[name], atol=1e-6, rtol=0)
        results.append({"width": width, "causal_padding_missingness_batch_gradient_resume": "passed",
                        "checkpoint": receipt})
    return {"status": "verified", "device": "cuda", "tolerance_absolute": 1e-6, "architectures": results}
