# secure_config_tool.py

import os
import json
import argparse
from cryptography.fernet import Fernet

def generate_key(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    key_path = os.path.join(output_dir, "secret.key")
    key = Fernet.generate_key()
    with open(key_path, "wb") as kf:
        kf.write(key)
    print(f"✅ Key saved to {key_path}")
    return key

def create_sample_config():
    return {
        "QA": {
            "Driver": "{SQL Server}",
            "Server": "your_qa_server",
            "Database": "your_qa_db",
            "UID": "your_qa_user",
            "PWD": "your_qa_password"
        },
        "PROD": {
            "Driver": "{SQL Server}",
            "Server": "your_prod_server",
            "Database": "your_prod_db",
            "Trusted_Connection": "yes"
        }
    }

def encrypt_config(key, output_dir, sample=False):
    config = create_sample_config()
    config_path_plain = os.path.join(output_dir, "db_config.json")
    config_path_encrypted = os.path.join(output_dir, "db_config.json.enc")

    if sample:
        with open(config_path_plain, "w") as jf:
            json.dump(config, jf, indent=4)
        print(f"✍️ Sample config written to {config_path_plain}")
    else:
        #with open(config_path_plain, "w") as jf:
          #  json.dump(config, jf)

        fernet = Fernet(key)
        with open(config_path_plain, "rb") as jf:
            plaintext = jf.read()
        encrypted = fernet.encrypt(plaintext)

        with open(config_path_encrypted, "wb") as ef:
            ef.write(encrypted)
        os.remove(config_path_plain)
        print(f"🔐 Encrypted config written to {config_path_encrypted}")

def decrypt_config(key_path, enc_path):
    with open(key_path, "rb") as kf:
        key = kf.read()
    fernet = Fernet(key)
    with open(enc_path, "rb") as ef:
        encrypted_data = ef.read()
    decrypted = fernet.decrypt(encrypted_data)
    config = json.loads(decrypted)
    print(json.dumps(config, indent=4))

def main():
    parser = argparse.ArgumentParser(description="Secure DB config tool")
    subparsers = parser.add_subparsers(dest="command")

    # Command: generate
    gen_parser = subparsers.add_parser("generate", help="Generate key + encrypted config")
    gen_parser.add_argument("--output", default="./secrets", help="Output directory")
    gen_parser.add_argument("--sample", action="store_true", help="Only create a sample config (no encryption)")

    # Command: decrypt
    dec_parser = subparsers.add_parser("decrypt", help="Decrypt and print the config")
    dec_parser.add_argument("--key", required=True, help="Path to secret.key")
    dec_parser.add_argument("--config", required=True, help="Path to db_config.json.enc")

    args = parser.parse_args()

    if args.command == "generate":
        key = generate_key(args.output)
        encrypt_config(key, args.output, sample=args.sample)

    elif args.command == "decrypt":
        decrypt_config(args.key, args.config)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
