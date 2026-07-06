# Security Policy

## Supported Version

Security fixes are targeted at the latest public version in `main`.

| Version | Supported |
| --- | --- |
| 1.2.x | Yes |
| Earlier versions | No |

## Reporting A Vulnerability

Please report vulnerabilities through GitHub issues if the report does not contain sensitive exploit details. For sensitive reports, contact the repository owner privately through GitHub.

Include:

- A short description of the issue
- Steps to reproduce
- Expected and actual behavior
- Any affected files or configuration

## Quant Lab Security Notes

Quant Lab strategy code is intentionally restricted. It blocks imports, file and network access, subprocess access, environment access, reflection helpers, and pandas write/export methods before execution. It also runs strategy code with a timeout and row limits.

These controls reduce risk but should not be treated as a hardened multi-tenant execution environment. Do not run this app as a public code-execution service without additional process isolation and infrastructure controls.
