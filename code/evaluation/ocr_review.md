# OCR implementation review

Measured on 2026-10-25. This report describes actual local execution and a release review; it does not claim a newer model was installed or benchmarked.

## Current implementation and measured coverage

The reproducible solution pins `rapidocr-onnxruntime==1.4.4`, executes OCR in a subprocess with a 180-second timeout and two inference threads, and caches text plus bounding boxes/confidence under an image SHA-256 and backend version. PDFs first use native text; sparse pages fall back to raster OCR. Screenshot business facts require explicit resource and owner identifiers in a visible row. Coordinates preserve row separation; uncertain text does not supply a guessed identifier.

All 11 supplied PNGs have nonempty cached OCR: 954 detected regions, 13,254 extracted characters, and three regions with confidence below 0.8. Confidence is an engine score, not independently measured character accuracy. The last full-run coverage checkpoint (`runs/20261025T105324913236Z/coverage.json`) admitted 24 image facts from nine PNGs. The customer reference registry is metadata; the object browser is business context without a supported subject/resource mapping. Neither is silently treated as evidence of successful deletion.

| Source | Regions | Regions below 0.8 | Admitted facts at checkpoint |
| --- | ---: | ---: | ---: |
| evidence_04 | 73 | 0 | 2 |
| evidence_09 | 70 | 0 | 2 |
| evidence_14 | 89 | 0 | 2 |
| evidence_19 | 90 | 1 | 2 |
| evidence_23 | 87 | 1 | 3 |
| evidence_28 | 74 | 0 | 1 |
| evidence_32 | 95 | 0 | 4 |
| evidence_37 | 106 | 0 | 6 |
| evidence_42 | 86 | 0 | 0 (metadata) |
| evidence_46 | 107 | 1 | 0 (context) |
| evidence_60 | 77 | 0 | 2 |

A visual spot-check compared three original PNGs with their cached output: the backup console, customer reference registry, and object storage browser. All six visible `backup_...` / `user_...` identifiers and all eight displayed object filenames were preserved exactly. This deliberately narrow check does not establish accuracy for every character, date, row association, or all eleven screenshots. The backup console shows an archive and retention end date; it does not expose a current restore permission for that archive. Better OCR cannot derive that absent control state.

The review fixed a real coverage bug: null/empty OCR, whitespace-only OCR and empty cached output now fail explicitly. They previously could become empty business context. Eight new regression cases exercise empty and malformed responses, including the existing-cache path. Targeted OCR/ingestion tests: **18 passed**. Complete test checkpoint after this change: **190 passed in 0.42 seconds**; later agent work may increase this count.

## Current release research

Official sources were checked on 2026-10-25:

- [PaddleOCR v3.7.0](https://github.com/PaddlePaddle/PaddleOCR/releases/tag/v3.7.0), released 2026-06-11, introduces PP-OCRv6. This is a newer conventional OCR candidate for the CPU screenshot workload. Its published aggregate improvements are upstream claims, not measurements on this dataset.
- [PaddleOCR v3.6.0](https://github.com/PaddlePaddle/PaddleOCR/releases/tag/v3.6.0), released 2026-05-28, includes PaddleOCR-VL-1.6 document parsing. Its layout/table capabilities merit an isolated comparison if exact row reconstruction remains a problem.
- [DeepSeek-OCR-2 official repository](https://github.com/deepseek-ai/DeepSeek-OCR-2) documents a CUDA 11.8/Torch 2.6 environment, Python 3.12.9 and vLLM/Flash Attention installation. No NVIDIA device or `nvidia-smi` executable was found in this workspace; the documented GPU setup has not been validated here.
- [Current RapidOCR repository](https://github.com/RapidAI/RapidOCR) documents the newer `rapidocr` package with ONNX Runtime and several inference backends. It is a migration candidate, rather than a drop-in version bump for the pinned `rapidocr_onnxruntime` import and tuple result API.

The source and dependency requirements differ. Replacing the backend without executing its models and checking identifier fidelity, source coordinates, dates, row boundaries, latency and memory would make the release less reproducible. This release retains the measured CPU backend and the fail-closed fix. A future comparison should use a separate environment and manually transcribed screenshot fixtures independent of public challenge answers, recording exact identifier/date recall, row-association errors, cold/warm latency and peak RSS. No evidence was sent to an OCR cloud service. No claim is made that this release uses the newest OCR model or that newer OCR can resolve missing source ownership or retention applicability.
