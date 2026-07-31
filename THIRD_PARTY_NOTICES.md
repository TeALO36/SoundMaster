# Third-party notices

This file records the principal third-party components and external content
referenced by SoundMaster. It is a starting point for the release audit, not a
substitute for checking the exact version, model revision, dependency license,
notice file, and terms applicable to a particular build.

## Original SoundMaster code

The original source code in this repository is available under the MIT License.
See [`LICENSE`](LICENSE).

## Python and desktop dependencies

SoundMaster currently declares or uses these principal packages:

- **PyQt6** — GUI toolkit. Check the installed PyQt6 and Qt license/notice files
  before redistribution. Upstream: <https://pypi.org/project/PyQt6/>.
- **huggingface_hub** — local Hugging Face repository download helper. Upstream:
  <https://github.com/huggingface/huggingface_hub>.
- **PyInstaller** — build-time packaging tool, not part of the application
  source license. Upstream: <https://github.com/pyinstaller/pyinstaller>.
- **pytest** and **ruff** — development-only tools. They are not intended to be
  bundled in the end-user application.

The actual generated distribution may include transitive libraries and Qt
runtime files. Preserve the notices required by the versions installed in the
build environment.

## Qwen3-TTS

SoundMaster can download these public repositories locally:

- <https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base>
- <https://huggingface.co/Qwen/Qwen3-TTS-Tokenizer-12Hz>
- upstream project: <https://github.com/QwenLM/Qwen3-TTS>

The model card and repository identify the applicable license and notices. The
exact model revision used by a release must be recorded in SoundMaster's legal
settings, together with its license reference, NOTICE reference, and checksum.
Do not assume that a future checkpoint, fine-tune, tokenizer, or dependency has
the same terms. Include the upstream license and NOTICE in a redistributable
bundle when required by those terms.

## OmniVoice

SoundMaster can download:

- <https://huggingface.co/k2-fsa/OmniVoice>
- upstream project: <https://github.com/k2-fsa/OmniVoice>

Review the repository license and every dependency or tokenizer used by the
specific release. Do not bundle OmniVoice weights or related assets until the
applicable notices and redistribution conditions have been verified.

## Hugging Face

Model downloads are performed from the public Hugging Face Hub. Hosting a model
on Hugging Face does not by itself grant a universal redistribution license.
Follow the model card, repository license, gated-model requirements, Hugging
Face terms, and any upstream asset terms for each model and revision.

## Myinstants and user-provided audio

SoundMaster does not grant rights to audio downloaded from Myinstants or any
other website. The Myinstants terms are available at:

<https://www.myinstants.com/en/terms_of_use.html>

Those terms describe personal, non-commercial access. Treat downloaded clips as
unlicensed for commercial redistribution unless written permission and the
rights to the underlying work have been obtained. User-provided sounds, music,
memes, recordings, and voice samples remain the user's responsibility.

## Voice, likeness, and consent

A voice sample may identify a person and may be regulated as personal or
biometric data depending on its use and jurisdiction. Only clone or imitate a
voice with appropriate authorization, document consent and deletion handling,
and obtain professional legal advice for the markets in which the application
is offered.

## Release audit checklist

Before publishing a build, the distributor should:

1. Record exact package versions and model revisions.
2. Collect upstream `LICENSE`, `NOTICE`, and attribution files required by those
   versions.
3. Verify that model weights, tokenizers, audio clips, and trademarks may be
   redistributed in the intended countries and sales channel.
4. Include or link the required notices in the installer and portable package.
5. Keep evidence of permission for every third-party audio asset.
6. Have the final bundle reviewed by qualified counsel where commercial rights
   are uncertain.
