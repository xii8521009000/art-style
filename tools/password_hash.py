import getpass
import hashlib
import secrets

if __name__ == '__main__':
    password = getpass.getpass('App password: ')
    salt = secrets.token_bytes(16)
    print(f'600000:{salt.hex()}:{hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000).hex()}')
