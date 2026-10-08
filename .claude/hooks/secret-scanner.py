#!/usr/bin/env python3
"""PreToolUse hook: scan for hardcoded secrets before a command commits them.

It runs BEFORE the command, so it cannot rely on the index alone: on
`git add . && git commit` nothing is staged yet at that point. See
pending_paths().

Adapted from claude-code-templates/secret-scanner for RAG-HP-PUB.

What is scanned (A195). For every `git add` / `git stage` / `git commit` the
command runs, in the repository THAT invocation targets -- `cd <dir> && ...`,
`git -C <dir>`, `--git-dir`/`--work-tree` are honoured, so a commit in another
repository is scanned there, not against the hook's own working directory:
  - the index, read as staged content (not the working-tree copy);
  - what the invocation is about to stage: `git add --dry-run <same arguments>`,
    i.e. git's own answer (`-f` on an ignored file included); the tracked changes
    for `commit -a`; the whole `git status` of that repository when an argument
    cannot be resolved statically (`$VAR`, `$(...)`) or the dry run fails;
  - the input files of `git apply --cached|--index`, `git hash-object -w` and
    `git update-index`, whose content goes into the object store directly.
A command that cannot be parsed falls back to the former behaviour: the whole
`git status` of the hook's working directory.

Known limit: the hook runs BEFORE the command and reads files as they are then.
`echo ... >> f && git add f` stages content the hook never saw, and so does a git
call made from inside a script (`bash x.sh`). Only a git-side pre-commit hook
would see those.
"""
import json
import os
import re
import shlex
import subprocess
import sys
from collections import namedtuple

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
    (r'mysql://[^@\s"\']+:[^@\s"\']+@[^\s"\']+', 'MySQL Connection String with Credentials', 'critical'),
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
    # This scanner's own test fixtures contain patterns by construction —
    # without this entry the scanner blocks every commit that touches its test.
    'test_secret_scanner.py',
}

EXCLUDE_DIRS = {'.git', 'node_modules', '.venv', '__pycache__', '.claude'}

# Internal-only hostnames common in Docker Compose / container environments.
# When a connection-string finding targets one of these AND the line is an
# env-var fallback (process.env.X || '...', os.environ.get('X', '...')), it
# is the documented internal default — not an exfilable secret.
INTERNAL_HOSTS = {
    'localhost', '127.0.0.1', '0.0.0.0', '::1',
    'redis', 'rabbitmq', 'postgres', 'postgresql', 'mongo', 'mongodb',
    'mysql', 'elasticsearch', 'milvus', 'qdrant', 'neo4j',
}

# Indicators that the URL on the line is an env-var fallback default.
ENV_FALLBACK_INDICATORS = (
    re.compile(r'process\.env\.'),
    re.compile(r'os\.environ\.get'),
    re.compile(r'os\.getenv'),
    re.compile(r'\bgetenv\s*\('),
    re.compile(r'\bSettings\b'),  # Pydantic BaseSettings field defaults
)

# Extract the host portion of a connection string to validate it is internal.
_CONN_HOST_RE = re.compile(
    r'(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis|amqp)://'
    r'(?:[^@/\s"\']+@)?'  # optional userinfo
    r'([^:/?\s"\']+)'      # host
)


# Case-insensitive: some generated artefacts carry a lowercased copy of a line
# (e.g. graphify's norm_label), turning ${REDIS_SECRET} into ${redis_secret}.
# Still requires an actual ${VAR} placeholder, so no literal credential passes.
_TEMPLATE_PLACEHOLDER_RE = re.compile(r'\$\{[A-Za-z_][A-Za-z0-9_]*\}')


def is_benign_default(line, finding_name):
    """Skip findings on env-var fallback lines targeting internal hosts,
    OR on connection strings that are fully templated (docker-compose
    style ${VAR} placeholders — no literal credentials at rest).

    Narrow allowlist: only applies to *Connection String findings.
    """
    if 'Connection String' not in finding_name:
        return False
    # docker-compose: fully templated URL like redis://:${REDIS_SECRET}@${REDIS_HOST}:${REDIS_PORT}
    if _TEMPLATE_PLACEHOLDER_RE.search(line):
        return True
    if not any(p.search(line) for p in ENV_FALLBACK_INDICATORS):
        return False
    m = _CONN_HOST_RE.search(line)
    if not m:
        return False
    return m.group(1).lower() in INTERNAL_HOSTS


# --- what a command does to a repository -----------------------------------

# prefix: the `git -C <dir> <global options>` the invocation runs with.
# stage: what it takes from the working tree, besides the index (see pending_paths);
#        None for a call that only feeds `sources` to the object store.
Target = namedtuple('Target', 'prefix stage sources')
NOTHING = ('none', ())
TRACKED = ('tracked', ())
SUPERSET = ('superset', ())

GIT_NAMES = {'git', 'git.exe'}
STAGING_SUBCOMMANDS = {'add', 'stage', 'commit'}
SOURCE_SUBCOMMANDS = {'apply', 'hash-object', 'update-index'}
GIT_GLOBAL_WITH_VALUE = {'-C', '-c', '--git-dir', '--work-tree', '--namespace', '--config-env'}
GIT_GLOBAL_PATHS = {'-C', '--git-dir', '--work-tree'}
ADD_INTERACTIVE = {'-p', '--patch', '-i', '--interactive', '-e', '--edit'}
COMMIT_SHORT_WITH_VALUE = set('mFCct')
COMMIT_LONG_WITH_VALUE = {'--message', '--file', '--reuse-message', '--reedit-message',
                          '--fixup', '--squash', '--author', '--date', '--template',
                          '--cleanup', '--trailer', '--pathspec-from-file'}
CD_COMMANDS = {'cd', 'chdir', 'pushd', 'set-location', 'sl', 'push-location'}
SHELLS = {'bash': 'bash', 'bash.exe': 'bash', 'sh': 'bash', 'sh.exe': 'bash',
          'pwsh': 'powershell', 'pwsh.exe': 'powershell',
          'powershell': 'powershell', 'powershell.exe': 'powershell'}
OPERATOR_CHARS = ';&|()<>\n'
REDIRECTS = {'>', '>>', '<', '<<', '<<-', '<<<', '>&', '<&', '&>', '&>>', '>|', '<>'}
HEREDOC_OPEN = re.compile(r'(?<!<)<<-?\s*([\'"]?)([A-Za-z_][A-Za-z0-9_]*)\1')
PS_HERESTRING_OPEN = re.compile(r'@([\'"])\s*$')
MSYS_DRIVE = re.compile(r'^/([A-Za-z])(?=/|$)')
ENV_ASSIGNMENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
LEGACY_TRIGGER = re.compile(r'\bgit\b.*\b(add|stage|commit|apply|hash-object|update-index)\b', re.S)


def strip_heredocs(command):
    """Drop here-document / here-string bodies: they are data, not commands."""
    kept, pending = [], []
    for line in command.split('\n'):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            elif pending[0] in ("'@", '"@') and line.startswith(pending[0]):
                pending.pop(0)
                kept.append(line[2:])           # `'@ | Out-File x` keeps its tail
            continue
        opening = PS_HERESTRING_OPEN.search(line)
        if opening:
            pending.append(opening.group(1) + '@')
            line = line[:opening.start()] + 'HERESTRING'
        pending.extend(m.group(2) for m in HEREDOC_OPEN.finditer(line))
        kept.append(line)
    if pending:
        raise ValueError('unterminated here-document')
    return '\n'.join(kept)


def tokenize(text, dialect):
    """Shell words and operators. Raises ValueError on unbalanced quotes."""
    lex = shlex.shlex(text, posix=True, punctuation_chars=OPERATOR_CHARS)
    lex.whitespace = ' \t\r'
    lex.whitespace_split = True
    lex.commenters = ''                 # a missed comment over-scans; an eaten command leaks
    if dialect == 'powershell':
        lex.escape = '`'                # backslashes are literal in Windows paths
    return list(lex)


def expand_path_word(word):
    """The expansions a shell would apply to a path word: $VAR, $env:VAR, ~, /d/.

    None when something is left that only the shell could resolve.
    """
    word = re.sub(r'(?i)\$env:([A-Za-z_][A-Za-z0-9_]*)',
                  lambda m: os.environ.get(m.group(1), m.group(0)), word)
    word = os.path.expandvars(word)
    if '$' in word or '`' in word:
        return None
    if word.startswith('~'):
        word = os.path.expanduser(word)
    if os.name == 'nt':
        word = MSYS_DRIVE.sub(lambda m: m.group(1).upper() + ':', word)
    return word


def change_dir(cwd, args):
    """Working directory after `cd <args>`; None when it cannot be known."""
    targets = [a for a in args if not a.startswith('-')]
    target = targets[0] if targets else '~'
    target = expand_path_word(target)
    if target is None or (cwd is None and not os.path.isabs(target)):
        return None
    path = os.path.normpath(os.path.join(cwd or '', target))
    return path if os.path.isdir(path) else None


def inline_script(args):
    """The script of `bash -c <script>` / `pwsh -Command <script>`, else None."""
    for i, arg in enumerate(args[:-1]):
        if arg.lower() in ('-c', '-command'):
            return args[i + 1]
    return None


def find_git_calls(command, dialect, cwd, depth=0):
    """[(cwd, words after `git`)] for every git invocation of a command line.

    Tracks `cd` across `&&`, `;`, `|` and restores it after a `( ... )` subshell.
    Raises ValueError when the command cannot be parsed.
    """
    tokens = tokenize(strip_heredocs(command), dialect)
    calls, stack, words, skip = [], [], [], False
    for tok in tokens + ['\n']:
        if skip:
            skip = False
            continue
        if not tok or any(c not in OPERATOR_CHARS for c in tok):
            words.append(tok)
            continue
        if tok in REDIRECTS:
            if words and words[-1].isdigit():   # `2>&1`: the fd is not an argument
                words.pop()
            skip = True                         # neither is the redirection target
            continue
        cwd = run_simple_command(words, cwd, dialect, calls, depth)
        words = []
        if '(' in tok:
            stack.append(cwd)
        if ')' in tok and stack:
            cwd = stack.pop()
    return calls


def run_simple_command(words, cwd, dialect, calls, depth):
    """Record a git call, follow a `cd`, recurse into `bash -c`. Returns the new cwd."""
    while words and ENV_ASSIGNMENT.match(words[0]):
        words = words[1:]
    if not words:
        return cwd
    head = os.path.basename(words[0]).lower()
    if head in CD_COMMANDS:
        return change_dir(cwd, words[1:])
    if head in SHELLS:
        script = inline_script(words[1:])
        if script is not None and depth < 3:
            calls.extend(find_git_calls(script, SHELLS[head], cwd, depth + 1))
        return cwd
    for i, word in enumerate(words):
        if os.path.basename(word).lower() in GIT_NAMES:
            calls.append((cwd, words[i + 1:]))
            break
    return cwd


def split_git_args(args):
    """`<global options> <subcommand> <arguments>` -> (options, subcommand, arguments)."""
    i = 0
    while i < len(args) and args[i].startswith('-'):
        i += 2 if args[i] in GIT_GLOBAL_WITH_VALUE else 1
    if i >= len(args):
        return args, None, []
    return args[:i], args[i], args[i + 1:]


def expand_global_options(options):
    """Expand the path values of -C/--git-dir/--work-tree; None if one is unresolvable.

    Relative values stay relative: git chains successive -C itself.
    """
    out, i = [], 0
    while i < len(options):
        opt = options[i]
        name, eq, value = opt.partition('=')
        if opt in GIT_GLOBAL_PATHS and i + 1 < len(options):
            value = expand_path_word(options[i + 1])
            if value is None:
                return None
            out += [opt, value]
            i += 2
            continue
        if eq and name in GIT_GLOBAL_PATHS:
            value = expand_path_word(value)
            if value is None:
                return None
            opt = f'{name}={value}'
        out.append(opt)
        i += 1
    return out


def is_dynamic(word):
    return '$' in word or '`' in word


def add_stage(args):
    if any(is_dynamic(a) for a in args) or ADD_INTERACTIVE & set(args):
        return SUPERSET
    return ('dry-run', tuple(args))


def commit_stage(args):
    """What `git commit <args>` takes from the working tree beyond the index."""
    pathspecs, extra, include_all, i = [], [], False, 0
    while i < len(args):
        arg = args[i]
        if arg == '--':
            pathspecs += args[i + 1:]
            break
        if arg.startswith('--'):
            name = arg.split('=', 1)[0]
            if name == '--all':
                include_all = True
            elif name == '--pathspec-from-file':
                value = arg.split('=', 1)[1] if '=' in arg else (args[i + 1] if i + 1 < len(args) else '')
                extra.append(f'--pathspec-from-file={value}')
            elif name == '--pathspec-file-nul':
                extra.append(arg)
            if name in COMMIT_LONG_WITH_VALUE and '=' not in arg:
                i += 1
        elif arg.startswith('-') and len(arg) > 1:
            for j, flag in enumerate(arg[1:]):
                if flag == 'a':
                    include_all = True
                if flag in COMMIT_SHORT_WITH_VALUE:
                    if j == len(arg) - 2:       # `-m msg`: the value is the next word
                        i += 1
                    break                       # `-mmsg`: the value is the rest of this one
        else:
            pathspecs.append(arg)
        i += 1
    if any(is_dynamic(p) for p in pathspecs + extra):
        return SUPERSET
    if include_all:
        return TRACKED
    if pathspecs or extra:
        return ('dry-run', tuple(extra + ['--'] + pathspecs))
    return NOTHING


def source_files(cwd, subcommand, args):
    """Files `apply --cached|--index`, `hash-object -w`, `update-index` read into git."""
    if subcommand == 'apply' and not {'--cached', '--index'} & set(args):
        return []
    if subcommand == 'hash-object' and '-w' not in args:
        return []
    files = []
    for arg in args:
        path = None if arg.startswith('-') else expand_path_word(arg)
        if path is not None and os.path.isfile(os.path.join(cwd, path)):
            files.append(os.path.join(cwd, path))
    return files


def git_prefix(cwd):
    return ('git', '-C', cwd)


def target_for_call(cwd, args, hook_cwd):
    options, subcommand, sub_args = split_git_args(args)
    if subcommand not in STAGING_SUBCOMMANDS | SOURCE_SUBCOMMANDS:
        return None
    options = expand_global_options(options)
    if cwd is None or options is None:
        return Target(git_prefix(hook_cwd), SUPERSET, ())   # former behaviour
    prefix = git_prefix(cwd) + tuple(options)
    if subcommand in ('add', 'stage'):
        return Target(prefix, add_stage(sub_args), ())
    if subcommand == 'commit':
        return Target(prefix, commit_stage(sub_args), ())
    return Target(prefix, None, tuple(source_files(cwd, subcommand, sub_args)))


def plan_targets(command, dialect, hook_cwd):
    """The repositories this command writes to, and what it puts in each."""
    try:
        calls = find_git_calls(command, dialect, hook_cwd)
    except ValueError:
        if LEGACY_TRIGGER.search(command):
            return [Target(git_prefix(hook_cwd), SUPERSET, ())]
        return []
    targets = []
    for cwd, args in calls:
        target = target_for_call(cwd, args, hook_cwd)
        if target is not None and target not in targets:
            targets.append(target)
    return targets


# --- reading what a target puts in the repository ---------------------------

def _run_git(args, binary=False):
    """stdout of a git call, or None when it fails."""
    try:
        result = subprocess.run(list(args), capture_output=True, stdin=subprocess.DEVNULL,
                                timeout=10)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout if binary else result.stdout.decode('utf-8', 'surrogateescape')


def split_z(out):
    return [p for p in (out or '').split('\0') if p]


def porcelain_paths(out):
    """Paths from `git status --porcelain -z`: `XY path`, and `XY new\\0old` for renames."""
    paths, items, i = [], out.split('\0'), 0
    while i < len(items):
        entry = items[i]
        i += 1
        if len(entry) < 4:
            continue
        if entry[0] in 'RC' or entry[1] in 'RC':
            i += 1                              # the source path of a rename/copy
        paths.append(entry[3:])
    return paths


def pending_paths(prefix, stage):
    """Paths, relative to the top of the work tree, that the call is about to stage.

    This hook runs BEFORE the command, so it cannot rely on the index alone: on
    `git add . && git commit -m ...` -- the dominant idiom -- nothing is staged
    yet at hook time, so looking only at the index returned an empty list and the
    secret went in completely unscanned.
    """
    kind, args = stage
    if kind == 'none':
        return []
    if kind == 'dry-run':
        out = _run_git(prefix + ('add', '--dry-run') + args)
        if out is not None:
            return [line[5:-1] for line in out.splitlines()
                    if line.startswith("add '") and line.endswith("'")]
        # The dry run failed: a superset is the safe direction here. An extra
        # finding on an unrelated dirty file costs a second of attention, a miss
        # costs a leaked credential.
        kind = 'superset'
    if kind == 'tracked':
        return split_z(_run_git(prefix + ('diff', '-z', '--name-only', '--diff-filter=ACMRT')))
    out = _run_git(prefix + ('status', '--porcelain', '-z', '--untracked-files=all'))
    return porcelain_paths(out or '')


def read_index_blobs(prefix, paths):
    """{path: staged content} -- what a commit takes, whatever the working tree holds."""
    if not paths:
        return {}
    request = ''.join(f':{p}\n' for p in paths).encode('utf-8', 'surrogateescape')
    try:
        out = subprocess.run(list(prefix) + ['cat-file', '--batch'], input=request,
                             capture_output=True, timeout=30).stdout
    except Exception:
        return {}
    blobs, pos = {}, 0
    for path in paths:
        end = out.find(b'\n', pos)
        if end < 0:
            break
        header = out[pos:end].split(b' ')
        pos = end + 1
        if len(header) != 3 or header[1] != b'blob':    # `<name> missing`
            continue
        size = int(header[2])
        blobs[path] = out[pos:pos + size]
        pos += size + 1
    return blobs


def is_excluded(relpath):
    relpath = relpath.replace('\\', '/')
    if any(relpath.startswith(d + '/') for d in EXCLUDE_DIRS):
        return True
    return relpath.split('/')[-1] in EXCLUDE_FILES


def scan_text(label, relpath, data):
    if is_excluded(relpath):
        return []
    findings = []
    for i, line in enumerate(data.decode('latin-1').split('\n'), 1):
        for pattern, name, severity in PATTERNS:
            if re.search(pattern, line) and not is_benign_default(line, name):
                findings.append((label, i, name, severity))
    return findings


def scan_file(filepath, relpath=None):
    """Scan a single file for secrets."""
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except OSError:
        return []
    return scan_text(filepath, filepath if relpath is None else relpath, data)


def collect_findings(target):
    findings = []
    for path in target.sources:
        findings += scan_file(path)
    if target.stage is None:
        return findings
    top = _run_git(target.prefix + ('rev-parse', '--show-toplevel'))
    if top is None:                 # not a repository: the command fails as well
        return findings
    top = top.strip()
    staged = split_z(_run_git(target.prefix + ('diff', '--cached', '-z', '--name-only',
                                               '--diff-filter=ACMR')))
    for path, data in read_index_blobs(target.prefix, staged).items():
        findings += scan_text(f'[index] {top}/{path}', path, data)
    for path in pending_paths(target.prefix, target.stage):
        findings += scan_file(f'{top}/{path}', path)
    return findings


def main():
    hook_input = json.loads(sys.stdin.read())
    tool_input = hook_input.get('tool_input', {})
    command = tool_input.get('command', '')

    # Only trigger on git commands
    if 'git' not in command.lower():
        sys.exit(0)

    dialect = 'powershell' if hook_input.get('tool_name') == 'PowerShell' else 'bash'
    hook_cwd = hook_input.get('cwd') or os.getcwd()
    all_findings = []
    for target in plan_targets(command, dialect, hook_cwd):
        all_findings.extend(collect_findings(target))
    all_findings = list(dict.fromkeys(all_findings))

    if not all_findings:
        sys.exit(0)

    # Block on critical/high findings
    critical = [f for f in all_findings if f[3] in ('critical', 'high')]
    if critical:
        msg = "🔴 BLOCKED: Potential secrets detected in files about to be committed:\n"
        for filepath, line, name, severity in critical:
            msg += f"  [{severity.upper()}] {filepath}:{line} — {name}\n"
        msg += "\nUse environment variables instead. See .claude/rules/security.md"
        print(msg, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == '__main__':
    main()
