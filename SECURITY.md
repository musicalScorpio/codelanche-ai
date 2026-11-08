# Security Policy

## Reporting a vulnerability

Please report security issues privately through GitHub's security advisory feature rather than a public issue.

## Security boundaries

Codelanche scans repositories as untrusted input. The scanner must never execute repository code. AI tools are read-only by default, and model-generated file or line references are verified against deterministic scan results before being accepted.
