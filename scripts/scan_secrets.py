#!/usr/bin/env python3
"""Local pre-publication scanner: heuristic; not proof of absence."""
from pathlib import Path
import re, subprocess, sys
root = Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
patterns = {
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'github_token': re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b'),
    'github_fine_grained': re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}\b'),
    'openai_key': re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'),
    'google_api': re.compile(r'\bAIza[0-9A-Za-z_-]{30,}\b'),
    'aws_key': re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'),
    'credential_assignment': re.compile(r'(?i)\b(?:api[_-]?key|secret|password|access[_-]?token)\s*[=:]\s*[\"\'](?!example|placeholder|changeme|YOUR_)[^\"\']{8,}'),
    'private_path': re.compile(r'(?:/home/[^/\s\"\']+|C:\\Users\\[^\\\s\"\']+)'),
    'hardware_serial': re.compile(r'\b5B7905071[0-9]\b'),
}
skipdirs={'.git','.venv','venv','__pycache__','backups','models','vosk-model-small-ja-0.22'}
allowed_ext={'.py','.sh','.md','.txt','.json','.yaml','.yml','.toml','.ini','.example','.gitignore'}
hits=[]
for path in root.rglob('*'):
    if not path.is_file() or any(x in skipdirs for x in path.relative_to(root).parts): continue
    if path.stat().st_size > 2_000_000 or (path.suffix not in allowed_ext and path.name not in {'.gitignore','.env.example'}): continue
    data=path.read_text(encoding='utf-8',errors='replace')
    for i,line in enumerate(data.splitlines(),1):
        for label,pattern in patterns.items():
            if path.resolve() == Path(__file__).resolve() and label == "private_path" and "re.compile" in line:
                continue
            if pattern.search(line): hits.append((str(path.relative_to(root)),i,label))
for path,line,label in hits: print(f'REVIEW {path}:{line} [{label}]')
print(f'Potential matches: {len(hits)}. 0 matches never guarantees safety; inspect git history, screenshots, videos and logs.')
sys.exit(1 if hits else 0)
