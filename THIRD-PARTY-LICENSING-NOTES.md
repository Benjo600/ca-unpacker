# Third-Party Open-Source Licensing Notes

## Purpose

CA Unpacker may use open-source libraries, OCR engines, PDF parsers, pretrained models, and other third-party components. Using open-source software in a paid/commercial product is normal, but every dependency must be checked for licensing obligations before release.

## Preferred license types

Prefer permissive licenses where possible:

- MIT
- BSD
- Apache-2.0

These are generally commercial-friendly, but attribution, copyright notices, NOTICE files, patent clauses, and redistribution requirements must still be followed.

## Higher-risk license types

Use extra caution with copyleft licenses such as:

- GPL
- LGPL
- AGPL

These are not automatically unusable, but depending on how a component is linked, bundled, modified, distributed, or accessed over a network, they can create additional source-code or redistribution obligations. Review them before inclusion in a proprietary release.

## Components discussed for CA Unpacker

### pdf-inspector

- Project: Firecrawl pdf-inspector
- License: MIT
- Intended use: fast/local PDF inspection and native-text extraction/routing
- Commercial use: generally permitted under MIT terms

### PaddleOCR

- Project: PaddlePaddle PaddleOCR
- License: Apache-2.0
- Intended use: stronger local OCR/document parsing for scanned or difficult documents
- Commercial use: generally permitted under Apache-2.0 terms
- Important: pretrained model weights and bundled assets should also be checked individually; do not assume they automatically have the same license as the code repository.

### Tesseract OCR

- Project: Tesseract OCR
- License: Apache-2.0
- Intended use: local OCR fallback / standard OCR engine
- Commercial use: generally permitted under Apache-2.0 terms
- Important: verify any bundled language data, Windows runtime files, and other redistributed dependencies before shipping.

## Model-weight licensing matters separately

For AI/OCR projects, always check both:

1. the software/library license; and
2. the license governing pretrained model weights, datasets, checkpoints, fonts, language packs, or bundled assets.

A permissive code license does not guarantee that every downloaded model or asset has identical commercial-use rights.

## Required release practice

Before every commercial release:

1. Generate an inventory of all bundled third-party components.
2. Record the exact package/version/model used.
3. Record its license and source URL.
4. Preserve all required copyright notices.
5. Include required LICENSE/NOTICE texts in the installer or installed application directory.
6. Confirm redistribution rights for native binaries and model weights.
7. Review any GPL/LGPL/AGPL dependency before shipping.
8. Re-run the audit whenever dependencies or models are upgraded.

## Recommended repository file

Maintain a release-facing file such as:

`THIRD_PARTY_LICENSES.md`

Example structure:

```text
pdf-inspector
License: MIT
Version: <version>
Source: <project URL>

PaddleOCR
License: Apache-2.0
Version: <version>
Model: <model/checkpoint>
Model License: <verified license>
Source: <project URL>

Tesseract OCR
License: Apache-2.0
Version: <version>
Source: <project URL>
```

The actual release file should contain the exact legally required notices/texts rather than only this summary.

## Privacy note

Open-source/local processing components can support CA Unpacker's privacy positioning because client documents can be processed on the user's own machine. However, privacy and licensing are separate concerns: a component can be fully local but still have redistribution obligations that must be respected.

## Product rule

**Prefer permissive, locally runnable components; verify both code and model licenses; document every bundled dependency before commercial distribution.**

> This document is an engineering/compliance checklist, not legal advice. For a paid commercial release, have the final third-party dependency inventory reviewed if there is any licensing uncertainty.
