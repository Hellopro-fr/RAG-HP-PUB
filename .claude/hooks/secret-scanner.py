#!/usr/bin/env python3
"""Pre-commit hook: scan staged files for hardcoded secrets.
Adapted from claude-code-templates/secret-scanner for RAG-HP-PUB.
"""
import json
import re
import subprocess
import sys

PATTERNS = [
    # Cloud providers
    (r'AKIA[0-9A-Z]{16}', 'AWS Access Key', 'critical'),
    (r'(?i)aws_secret_access_key\s*=\s*["\'][^"\']+["\']', 'AWS Secret Key', 'critical'),
    # Anthropic
    (r'sk-ant-api\d{2}-[A-Za-z0-9_-]{80,}', 'Anthropic API Key', 'critical'),
    # OpenAI
    (r'sk-[A-Za-z0-9]{20,}', 'OpenAI API Key', 'critical'),
    # Google
    (r'AIza[0-9A-Za-z_-]{35}', 'Google API Key', 'high'),
    # Stripe
    (r'sk_live_[0-9a-zA-Z]{24,}', 'Stripe Live Secret', 'critical'),
    (r'sk_test_[0-9a-zA-Z]{24,}', 'Stripe Test Secret', 'medium'),
    # GitHub
    (r'ghp_[0-9a-zA-Z]{36}', 'GitHub PAT', 'critical'),
    (r'gho_[0-9a-zA-Z]{36}', 'GitHub OAuth', 'critical'),
    (r'github_pat_[0-9a-zA-Z_]{82}', 'GitHub Fine-grained PAT', 'critical'),
    # GitLab
    (r'glpat-[0-9a-zA-Z_-]{20,}', 'GitLab PAT', 'critical'),
    # Vercel / Supabase / HuggingFace
    (r'vercel_[0-9a-zA-Z_-]{24,}', 'Vercel Token', 'high'),
    (r'sbp_[0-9a-f]{40}', 'Supabase Service Key', 'critical'),
    (r'hf_[0-9a-zA-Z]{34}', 'HuggingFace Token', 'high'),
    # Database connection strings
    (r'mongodb(\+srv)?://[^\s"\']+', 'MongoDB Connection String', 'critical'),
    (r'postgres(ql)?://[^\s"\']+', 'PostgreSQL Connection String', 'critical'),
    (r'mysql://[^\s"\']+', 'MySQL Connection String', 'critical'),
    (r'redis://[^\s"\']+', 'Redis Connection String', 'high'),
    (r'amqp://[^\s"\']+', 'RabbitMQ Connection String', 'high'),
    # JWT / Private keys
    (r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', 'JWT Token', 'high'),
    (r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', 'Private Key', 'critical'),
    # Generic patterns
    (r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{8,}["\']', 'Hardcoded Password', 'high'),
    (r'(?i)(api_key|apikey|api-key)\s*=\s*["\'][^"\']{16,}["\']', 'Hardcoded API Key', 'high'),
    (r'(?i)(secret|token)\s*=\s*["\'][^"\']{16,}["\']', 'Hardcoded Secret/Token', 'high'),
    # Slack / Discord / Telegram
    (r'xoxb-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24}', 'Slack Bot Token', 'critical'),
    (r'https://hooks\.slack\.com/services/[A-Za-z0-9/]+', 'Slack Webhook', 'high'),
    (r'https://discord(app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+', 'Discord Webhook', 'high'),
]

EXCLUDE_FILES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'Cargo.lock',
    'poetry.lock', 'requirements.lock', '.env.example', '.env.template',
}

EXCLUDE_DIRS = {'.git', 'node_modules', '.venv', '__pycache__', '.claude'}


def get_staged_files():
    """Get list of staged files."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR'],
            capture_output=True, text=True, timeout=10
        )
        return [f for f in result.stdout.strip().split('\n') if f]
    except Exception:
        return []


def scan_file(filepath):
    """Scan a single file for secrets."""
    if any(filepath.startswith(d + '/') for d in EXCLUDE_DIRS):
        return []
    if filepath.split('/')[-1] in EXCLUDE_FILES:
        return []

    findings = []
    try:
        with open(filepath, 'r', errors='ignore') as f:
            for i, line in enumerate(f, 1):
                for pattern, name, severity in PATTERNS:
                    if re.search(pattern, line):
                        findings.append((filepath, i, name, severity))
    except (FileNotFoundError, PermissionError):
        pass
    return findings


def main():
    hook_input = json.loads(sys.stdin.read())
    tool_input = hook_input.get('tool_input', {})
    command = tool_input.get('command', '')

    # Only trigger on git commit commands
    if 'git commit' not in command and 'git add' not in command:
        sys.exit(0)

    files = get_staged_files()
    if not files:
        sys.exit(0)

    all_findings = []
    for f in files:
        all_findings.extend(scan_file(f))

    if not all_findings:
        sys.exit(0)

    # Block on critical/high findings
    critical = [f for f in all_findings if f[3] in ('critical', 'high')]
    if critical:
        msg = "🔴 BLOCKED: Potential secrets detected in staged files:\n"
        for filepath, line, name, severity in critical:
            msg += f"  [{severity.upper()}] {filepath}:{line} — {name}\n"
        msg += "\nUse environment variables instead. See .claude/rules/security.md"
        print(msg, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == '__main__':
    main()
