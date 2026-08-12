# Security policy

## Supported versions

Security fixes are provided for the latest tagged release and the `main`
branch while KITE remains pre-1.0.

## Report a vulnerability

Please use GitHub's private vulnerability reporting for
[`memoket/KITE`](https://github.com/memoket/KITE/security/advisories/new).
Do not open a public issue containing credentials, private conversation data,
or an unpatched exploit. Include affected versions, reproduction steps, and the
expected impact. We will acknowledge a report as soon as maintainers can triage
it and coordinate disclosure with the reporter.

KITE processes conversational data and sends prompt content to the configured
LLM endpoint. Applications are responsible for confirming that their data
handling and provider configuration satisfy their privacy requirements.
