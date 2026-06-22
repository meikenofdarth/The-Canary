"""Pre-download all model weights at image-build time so the container runs
offline and the first request is warm. Run from the project root (/app)."""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    print("[prefetch] downloading Silero VAD ...")
    from silero_vad import load_silero_vad
    load_silero_vad()
    print("[prefetch] Silero VAD cached")

    print("[prefetch] downloading ConvTasNet (noisy) ...")
    from computation.audio.separator import _get_model
    _get_model("noisy")
    print("[prefetch] ConvTasNet noisy cached")

    print("[prefetch] downloading ConvTasNet (clean) ...")
    _get_model("clean")
    print("[prefetch] ConvTasNet clean cached")

    print("[prefetch] downloading ECAPA-TDNN ...")
    from speechbrain.inference.speaker import EncoderClassifier
    EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="pretrained_models/spkrec-ecapa-voxceleb",
        run_opts={"device": "cpu"},
    )
    print("[prefetch] ECAPA-TDNN cached")

    print("[prefetch] downloading Whisper tiny ...")
    import whisper
    whisper.load_model("tiny")
    print("[prefetch] Whisper tiny cached")

    print("[prefetch] ALL models cached — subsequent runs will be instant")


if __name__ == "__main__":
    main()
