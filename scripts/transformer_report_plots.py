"""Render saved Transformer metrics with Matplotlib/Agg; never execute a model."""
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


def render(result: dict, counts: dict, output: Path) -> list[str]:
    """Plot already-validated epoch metrics and selected-checkpoint row counts."""
    output.mkdir(parents=True, exist_ok=True)
    history = result["progress"]["history"]
    epochs = [row["epoch"] for row in history]
    selected = result["selected_epoch"]
    trial = result["trial"]
    identity = (f"Width {trial['width']} | Learning rate {trial['learning_rate']:g}"
                f" | Seed {trial['seed']}")
    figure = Figure(figsize=(9, 9), dpi=120, facecolor="white", layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots(3, 1, sharex=True)
    series = (
        ("weighted_train_loss", "Training loss: class/session weighted", "Weighted BCE", "#1769aa"),
        ("selection_log_loss", "Selection loss: unweighted", "Raw log loss", "#b45309"),
        ("selection_f1_at_half", "Selection F1: raw probability threshold 0.5", "F1", "#177245"),
    )
    for axis, (key, title, label, color) in zip(axes, series):
        values = [row[key] for row in history]
        axis.plot(epochs, values, color=color, marker="o", markersize=4, linewidth=1.7)
        axis.axvline(selected, color="black", linestyle="--", linewidth=1.2,
                     label=f"Selected checkpoint: epoch {selected}")
        axis.set(title=title, ylabel=label, xlim=(0.5, epochs[-1] + 0.5))
        axis.set_xticks(epochs)
        axis.set_ylim(0, 1 if key == "selection_f1_at_half" else max(0.01, max(values) * 1.12))
        axis.grid(axis="y", color="#d8dee5", linewidth=0.7)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].legend(loc="upper right", fontsize=9)
    axes[-1].set_xlabel("Epoch")
    figure.suptitle("Transformer learning curves\n" + identity, fontsize=14)
    figure.supxlabel("Losses use different weighting; their gap is not directly comparable.", fontsize=10)
    learning_name = "learning-curves.png"
    figure.savefig(output / learning_name, facecolor="white")

    matrix = [[counts["tn"], counts["fp"]], [counts["fn"], counts["tp"]]]
    positives = counts["fn"] + counts["tp"]
    total = sum(counts[key] for key in ("tn", "fp", "fn", "tp"))
    figure = Figure(figsize=(8, 6), dpi=140, facecolor="white", layout="constrained")
    FigureCanvasAgg(figure)
    axis = figure.subplots()
    maximum = max(1, *(value for row in matrix for value in row))
    heatmap = axis.imshow(matrix, cmap="Blues", vmin=0, vmax=maximum, interpolation="nearest")
    axis.set(xticks=[0, 1], yticks=[0, 1], xlabel="Predicted label", ylabel="Actual label")
    axis.set_xticklabels(["Negative (0)", "Positive (1)"])
    axis.set_yticklabels(["Negative (0)", "Positive (1)"])
    names = (("True negatives", "False positives"), ("False negatives", "True positives"))
    for row in range(2):
        for column in range(2):
            value = matrix[row][column]
            axis.text(column, row, f"{names[row][column]}\n{value:,}", ha="center", va="center",
                      fontsize=13, color="white" if value > maximum * 0.55 else "#10243a")
    figure.colorbar(heatmap, ax=axis, shrink=0.8, label="Number of selection rows")
    figure.suptitle(f"Selection confusion matrix: epoch {selected}\n" + identity, fontsize=13)
    axis.set_title(f"{total:,} rows; {positives:,} actual positives | Raw probability threshold 0.5",
                   fontsize=10, pad=12)
    figure.supxlabel("Selection data is used for tuning; probabilities are uncalibrated.", fontsize=10)
    confusion_name = "confusion-matrix.png"
    figure.savefig(output / confusion_name, facecolor="white")
    return [learning_name, confusion_name]
