# Security Policy

## Supported Versions

Only the latest release, or the default branch if there are no releases, receives security fixes.

## Reporting a Vulnerability

Please don't report vulnerabilities through public issues, pull requests or discussions. Use GitHub's private vulnerability reporting instead (the repository's **Security** tab → **Report a vulnerability**). If that's unavailable, contact me at the email address on my GitHub profile.

Please include a description and the potential impact, steps to reproduce or a proof of concept, and the affected version, commit or configuration.

This is a personal project maintained on a best-effort basis. I aim to acknowledge reports within 7 days and will keep you updated. Once a fix is released you'll be credited in the advisory unless you prefer to stay anonymous.

## Scope and Threat Model

img tagger is a local Python CLI. It sends images to an Ollama or LM Studio server chosen by the operator and writes the returned tags into image metadata, or clears metadata without contacting a server. It exposes no inbound service. In scope: `img_tagger.py`, its dependencies and configuration, and the GitHub Actions workflows. Tests and documentation show intended behavior; they don't prove that the controls hold.

The operator chooses the image folders, server, model, prompt and log path. Images, metadata, file names and model replies may be controlled by an attacker and stay untrusted data. Relevant attackers include image suppliers, other local users who can change filesystem entries the operator can reach, malicious model servers, and contributors submitting pull requests. Assets are image contents, unrelated local files, file permissions, logs and CI credentials.

There is no isolation from root or from other processes running as the operator. That doesn't excuse flaws reachable through attacker-controlled images processed with the operator's privileges.

## Security Invariants

- Image reads reject nonregular files and symlink/reparse-point redirection; backend clients and image libraries get guarded byte snapshots and never reopen paths.
- Metadata edits stay within the intended image and its folder. Temporary files are created exclusively there, kept open through all writes, and replaced or removed safely.
- Temporary and replaced images never grant more access than the source (mode, group, ACLs, DACLs, EFS encryption). If permissions can't be preserved, the edit fails or uses the documented narrower fallback.
- Model replies and metadata are data: they never trigger commands, other file operations or new network destinations. The clients follow no redirects and send no API keys from the environment.
- Logs must be regular `.log` files owned by the operator, are opened without following a leaf link, and new logs are private.
- CI must not expose credentials or write access to untrusted contributions.

## Reportable Findings

Report reachable violations with concrete attacker control, prerequisites and impact on confidentiality, integrity or availability, e.g. unintended file reads or writes, permission widening, data disclosure, unsafe native parsing or CI credential exposure. Assess severity for this local CLI and the user interaction it needs; neither local execution nor a passing test alone makes a finding harmless. No class of finding is excluded outright.

## Known Limitations

- The copy sent to the model has no metadata, but `--max-pixels 0` and failed copy preparation send the original bytes, metadata included. The chosen server receives the images, so trust in it and in the network path matters. Logs contain paths and raw replies.
- The `[PROCESSED BY AI]` marker is unauthenticated and causes a skip. `--clear` and metadata repair remove metadata by design, and repair can re-encode pixels.
- Resource limits are partial: files over 256 MiB and animation repairs over 250 million pixels are refused, and logged replies are cut at 4000 characters, but model replies and image decoding have no general memory budget.
- Windows FAT32/exFAT and network shares are untested. On Windows, anyone who can write an image's folder can race the final rename (only within that pinned folder), and folders granting neither traverse nor list access can't be pinned and are refused. POSIX protection relies on the image folder's ownership and write restrictions.

These document current behavior, not blanket risk acceptance; further exclusions need the owner's confirmation.
