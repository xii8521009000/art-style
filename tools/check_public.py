"""Scan the exact staged/tracked file set without printing possible secrets."""
from pathlib import Path
import hashlib
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PRIVATE_PARTS={'.venv','node_modules','dist','test-results','regression','private','.codex','data','__pycache__'}
# Exact byte copies of visually reviewed, metadata-checked public fixture captures only.
# Updating a screenshot requires a new privacy review before changing its digest.
APPROVED_SCREENSHOTS={
    'docs/screenshots/codex-login.jpg':'0ca621e1014c5e91b216278e8641b008f0f209dd4c2311b303de7c886b40dbea',
    'docs/screenshots/codex-settings.jpg':'9dc860637fbde07f5a61c2808765dc609454bc411e538088970c7225b6eafd4c',
    'docs/screenshots/external-request.jpg':'92e7b53ffb7ce93919ca50fc845a55e00a3b3c264c3aedcb3694b714c76401ad',
    'docs/screenshots/json-import.jpg':'109f5408c24b81ad1039c94c57dcb8115ac794c7cb02036abaea25516975b00f',
    'docs/screenshots/library-detail.jpg':'3237df893c926ea7de346e9f466063d04b06e36b3bfb54fdbdd4a69521bc881c',
    'docs/screenshots/new-analysis.jpg':'ce701587b2d464fffd279776c0dbb32b0f67712b47347c7c521d3391ed408e30',
}
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


def approved_screenshot(filename,body):
    return filename in APPROVED_SCREENSHOTS and body.startswith(b'\xff\xd8') and body.endswith(b'\xff\xd9') and hashlib.sha256(body).hexdigest()==APPROVED_SCREENSHOTS[filename]


def verify():
    problems=[]
    files=tracked_files()
    for filename in files:
        path=Path(filename)
        body=staged_bytes(filename)
        if path.suffix.lower() in {'.webp','.png','.jpg','.jpeg'} and not approved_screenshot(filename,body):
            problems.append((filename,'unreviewed image'));continue
        if any(part in PRIVATE_PARTS for part in path.parts) or (path.name.startswith('.env') and path.name!='.env.example') or path.name in {'auth.json','compose.override.yaml','compose.override.yml'} or path.suffix.lower() in {'.dump','.sql','.zip','.log','.pyc'} or filename.endswith('.tar.gz'):
            problems.append((filename,'private artifact'));continue
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
