"""Create one installation's private .env without printing or accepting passwords in argv."""
import argparse
import getpass
import hashlib
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://localhost:8080')
    parser.add_argument('--username',default='admin')
    parser.add_argument('--port',type=int,default=8080)
    args=parser.parse_args()
    url=args.url.rstrip('/')
    parsed=urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username or not re.fullmatch(r'https?://[A-Za-z0-9.\-:\[\]]+',url):
        raise SystemExit('--url must be an http(s) origin without a path or user information')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',args.username) or not 1024<=args.port<=65535:
        raise SystemExit('Choose a valid username and a port between 1024 and 65535')
    destination=Path(__file__).resolve().parents[1]/'.env'
    if destination.exists():
        raise SystemExit('Existing .env preserved. Back it up and edit it explicitly if changes are needed.')
    password=getpass.getpass('New workspace password (12+ characters): ')
    if len(password)<12 or password!=getpass.getpass('Repeat password: '):
        raise SystemExit('Passwords must match and contain at least 12 characters')
    salt=secrets.token_bytes(16)
    hashed=f'600000:{salt.hex()}:{hashlib.pbkdf2_hmac("sha256",password.encode(),salt,600000).hex()}'
    values={'APP_PORT':args.port,'APP_URL':url,'APP_USERNAME':args.username,'APP_PASSWORD_HASH':hashed,
            'POSTGRES_PASSWORD':secrets.token_hex(32),'APP_DB_PASSWORD':secrets.token_hex(32),
            'ENGINE_TOKEN':secrets.token_urlsafe(48),'COOKIE_SECURE':str(parsed.scheme=='https').lower()}
    descriptor=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8',newline='\n') as output:
        output.write(''.join(f'{key}={value}\n' for key,value in values.items()))
    print('Created private .env. Do not commit or share this file.')


if __name__=='__main__': main()
