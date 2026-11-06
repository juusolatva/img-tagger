# Security Policy

## Supported Versions

Only the latest release, or the default branch if there are no releases,
receives security fixes.

## Reporting a Vulnerability

Please do not report security vulnerabilities through public issues,
pull requests, or discussions.

Report them privately through GitHub's private vulnerability reporting:

1. Go to the repository's Security tab.
2. Click Report a vulnerability.

If that option is unavailable, please contact me using the email address
on my GitHub profile.

Please include:

- A description of the issue and its potential impact
- Steps to reproduce, or a proof of concept
- Affected version, commit, or configuration

## What to Expect

This is a personal project maintained on a best-effort basis. I aim to
acknowledge reports within 7 days and will keep you updated on progress.
Once a fix is released, you will be credited in the advisory unless you
prefer to remain anonymous.

## System and Scope

img-tagger is a local Python CLI that sends images to an operator-selected
Ollama or LM Studio backend and writes generated tags into image metadata.
It can also clear metadata without contacting a backend. It does not expose
an inbound application service.

Review scope includes img_tagger.py, dependencies, configuration, and GitHub
Actions workflows. Tests and documentation provide evidence of intended
behavior, not proof that security controls hold.

## Threat Model and Trust Boundaries

The operator selects image directories, backend addresses, models, prompts,
and log destinations. Images, metadata, filenames, and model replies may
contain attacker-controlled data. Processing an image does not make its
contents or the model's response trusted.

Assets include image contents, unrelated local files, filesystem permissions,
logs, and CI credentials. Relevant attackers include image suppliers,
other local users able to manipulate accessible filesystem entries, malicious
backend responses, and contributors submitting untrusted pull requests.

The documented local deployment does not provide isolation from root or
another process running as the operator. This assumption does not exempt
attacker-controlled images processed with the operator's privileges.

## Security Invariants

- Image reads must reject nonregular files and symlink/reparse-point
  redirection under the documented platform constraints. Backend clients and
  image libraries must receive guarded snapshots rather than reopen paths.
- Metadata edits must remain confined to the intended image directory and
  target. Temporary files must be exclusively created there, retain their
  handles through writes, and be safely replaced or cleaned up.
- Temporary and committed images must not grant unintended access through
  modes, groups, inherited ACLs, or DACLs. Failed permission preservation
  must fail closed or use the documented narrower-permission fallback.
- Model replies and image metadata must remain data; they must not authorize
  commands, additional filesystem operations, or new network destinations.
- CLI logs must use regular .log files, reject leaf links, and retain the
  opened stream. POSIX logs must belong to the operator; new logs are private.
- CI must not expose privileged credentials or write capabilities to
  untrusted contributions through workflow execution or artifact handling.

## Reportable Findings and Severity Context

Report reachable violations with concrete attacker control, prerequisites,
and confidentiality, integrity, or availability impact. Relevant examples
include unintended file reads or writes, permission widening, data disclosure,
unsafe native parsing, and CI credential exposure.

Assess severity using this local CLI deployment and required user interaction.
Neither local execution nor a passing test alone makes a finding harmless.
No finding class is categorically excluded by this policy.

## Known Limitations and Unresolved Risk Decisions

Metadata-free model images are not a confidentiality guarantee: --max-pixels
0 and preparation failures send original bytes, including original metadata.
The selected backend receives those bytes; logs can contain raw replies and
paths. Backend transport and deployment trust must be considered.

The processing marker is unauthenticated and can cause a skip. Metadata
clearing and repair intentionally remove metadata; repair can re-encode
pixels. These behaviors do not authorize modification of unrelated files.

Input bytes, animation frames, and model replies have no comprehensive
resource budget. The model pixel limit is not a general memory limit.

Windows FAT32/exFAT and network shares are untested. Windows directory
writers can race leaf replacement; some ancestor access modes prevent
pinning. POSIX protection depends on final-directory ownership and write
restrictions. Evaluate findings against the actual platform and permissions.

These limitations document current behavior, not blanket risk acceptance.
Any additional exclusions or accepted risks require owner confirmation.
