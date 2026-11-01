"""Scan the exact staged/tracked file set without printing possible secrets."""
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PRIVATE_PARTS={'.venv','node_modules','dist','test-results','regression','private','.codex','data','__pycache__'}
PATTERNS={
    'private key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'OpenAI key':re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}'),
    'JWT':re.compile(rb'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}'),
    'password hash':re.compile(rb'\b600000:[a-f0-9]{32}:[a-f0-9]{64}\b'),
    'private address':re.compile(rb'\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b'),
    'Windows personal path':re.compile(rb'\b[A-Za-z]:[\\/](?:Users|Dev_E|CodexData)[\\/]',re.I),
}


def tracked_files():
    result=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True)
    files=[name for name in result.stdout.decode('utf-8').split('\0') if name]
    if not files:raise RuntimeError('No tracked/staged files. Add only the intended public source files first.')
    return files


def staged_bytes(filename):
    return subprocess.run(['git','show',':'+filename],cwd=ROOT,capture_output=True,check=True).stdout


def verify():
    problems=[]
    files=tracked_files()
    for filename in files:
        path=Path(filename)
        if any(part in PRIVATE_PARTS for part in path.parts) or (path.name.startswith('.env') and path.name!='.env.example') or path.name in {'auth.json','compose.override.yaml','compose.override.yml'} or path.suffix.lower() in {'.dump','.sql','.zip','.webp','.png','.jpg','.log','.pyc'} or filename.endswith('.tar.gz'):
            problems.append((filename,'private artifact'));continue
        body=staged_bytes(filename)
        for label,pattern in PATTERNS.items():
            if pattern.search(body):problems.append((filename,label))
    if problems:
        for filename,kind in problems: print(f'REJECT: {filename}: {kind}')
        raise RuntimeError('Public file check failed. Values are intentionally omitted.')
    print(f'PASS: {len(files)} public files; no private artifacts or recognized credential/address patterns.')
    return files


if __name__=='__main__':
    try:verify()
    except (RuntimeError,subprocess.CalledProcessError) as exc:
        print(type(exc).__name__+': public file verification failed.',file=sys.stderr)
        sys.exit(1)
