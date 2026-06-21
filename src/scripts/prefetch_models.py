"""Pre-download all model weights at image-build time so the container runs
offline and the first request is warm. Run from the project root (/app)."""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    # Separation: both ConvTasNet variants the auto-selector can pick.
    from computation.audio.separator import _get_model
    _get_model("noisy")
    _get_model("clean")

    # Speaker biometrics: ECAPA-TDNN (savedir is relative to CWD = /app).
    from speechbrain.inference.speaker import EncoderClassifier
    EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="pretrained_models/spkrec-ecapa-voxceleb",
        run_opts={"device": "cpu"},
    )

    # ASR: Whisper tiny.
    import whisper
    whisper.load_model("tiny")

    print("[prefetch] all models cached")


if __name__ == "__main__":
    main()
