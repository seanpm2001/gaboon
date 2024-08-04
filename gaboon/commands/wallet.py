import json
import getpass
from pathlib import Path
import shutil
from typing import Any, List
from gaboon.logging import logger
from gaboon.constants.vars import DEFAULT_KEYSTORES_PATH
from eth_account import Account as EthAccountsClass
from eth_account.signers.local import LocalAccount
from hexbytes import HexBytes
from eth_account.types import (
    PrivateKeyType,
)
from argparse import Namespace


def main(args: Namespace) -> int:
    if args.wallet_command == "list":
        list_accounts()
        return 0
    elif args.wallet_command == "generate":
        return generate_account(
            args.name,
            args.save,
            password=args.password,
            password_file=args.password_file,
        )
    elif args.wallet_command == "import":
        return import_private_key(args.name)
    elif args.wallet_command == "delete":
        return delete_keystore(args.keystore_file_name)
    elif args.wallet_command == "inspect":
        inspect(args.keystore_file_name)
    elif args.wallet_command == "decrypt":
        return decrypt_key(
            args.keystore_file_name,
            password=args.password,
            password_file_path=args.password_file_path,
            print_key=args.print_key,
        )
    else:
        logger.error(f"Unknown accounts command: {args.wallet_command}")
        return 1


def inspect(
    keystore_file_name: str, keystores_path: Path = DEFAULT_KEYSTORES_PATH
) -> dict:
    keystore_path = keystores_path.joinpath(keystore_file_name)
    if not keystore_path.exists():
        logger.error(
            f"Account with name {keystore_file_name} does not exist in keystores"
        )
        return
    try:
        with keystore_path.open("r") as fp:
            keystore = json.load(fp)
        logger.info(f"Keystore JSON for account {keystore_file_name}:")
        logger.info(json.dumps(keystore, indent=4))
    except Exception as e:
        logger.error(
            f"Failed to read account {keystore_file_name} from keystores: {str(e)}"
        )
    return keystore


def list_accounts(
    keystores_path: Path = DEFAULT_KEYSTORES_PATH,
) -> list[Any] | None:
    if keystores_path.exists():
        account_paths = sorted(keystores_path.glob("*"))
        logger.info(
            f"Found {len(account_paths)} account{'s' if len(account_paths)!=1 else ''}:"
        )
        for path in account_paths:
            logger.info(f"{path.stem}")
        return account_paths
    else:
        logger.info(f"No accounts found at {keystores_path}")
        return None


def generate_account(
    name: str, save: bool = False, password: str = None, password_file: str = None
) -> int:
    logger.info("Generating new account...")
    new_account: LocalAccount = EthAccountsClass.create()
    if save:
        if password:
            save_to_keystores(
                name,
                new_account,
                password=password,
                keystores_path=DEFAULT_KEYSTORES_PATH,
            )
        elif password_file:
            save_to_keystores(
                name,
                new_account,
                password_file=Path(password_file),
                keystores_path=DEFAULT_KEYSTORES_PATH,
            )
        else:
            logger.error("No password provided to save account")
            return 1
    else:
        logger.info(f"Account generated: {new_account.address}")
        logger.info(f"(Unsafe) Private key: {new_account.key}")
        logger.info(
            f"To save, add the --save flag next time with:\ngab wallet generate {name} --save --password <password>"
        )
    return 0


def save_to_keystores(
    name: str,
    account_or_key: LocalAccount | PrivateKeyType,
    password: str = None,
    password_file: Path | None = None,
    keystores_path: Path = DEFAULT_KEYSTORES_PATH,
):
    if not isinstance(account_or_key, LocalAccount):
        account_or_key = EthAccountsClass.from_key(account_or_key)
    new_keystore_path = keystores_path.joinpath(name)
    if new_keystore_path.exists():
        logger.error(f"Account with name {name} already exists")
        return 1
    new_keystore_path.parent.mkdir(parents=True, exist_ok=True)
    if password:
        encrypted: dict[str, Any] = account_or_key.encrypt(password)
    elif password_file:
        password_file = Path(password_file).expanduser().resolve()
        with password_file.open("r") as fp:
            password = fp.read()
        encrypted: dict[str, Any] = account_or_key.encrypt(password)
    else:
        logger.error("No password provided to save account")
        return 1
    with new_keystore_path.open("w") as fp:
        json.dump(encrypted, fp)
    logger.info(f"Saved account {name} to keystores!")


def import_private_key(
    name: str,
    private_key: str | None = None,
    password: str | None = None,
    keystores_path: Path = DEFAULT_KEYSTORES_PATH,
) -> int:
    logger.info("Importing private key...")
    if not private_key:
        while True:
            private_key = getpass.getpass("Enter your private key: ")
            if private_key:
                break
            logger.error("Private key cannot be empty. Please try again.")

    # Step 2 & 3: Get password and confirmation
    if not password:
        while True:
            password = getpass.getpass("Enter a password to encrypt your key: ")
            if not password:
                logger.error("Password cannot be empty. Please try again.")
                continue

            password_confirm = getpass.getpass("Confirm your password: ")
            if password == password_confirm:
                break
            logger.error("Passwords do not match. Please try again.")

    new_account: LocalAccount = EthAccountsClass.from_key(private_key)
    save_to_keystores(
        name,
        new_account,
        password=password,
        keystores_path=keystores_path,
    )


def delete_keystore(
    name: str,
    keystores_path: Path = DEFAULT_KEYSTORES_PATH,
) -> int:
    keystore_path = keystores_path.joinpath(name)

    if not keystore_path.exists():
        logger.error(f"Account with name {name} does not exist in keystores")
        return 1

    try:
        if keystore_path.is_dir():
            shutil.rmtree(keystore_path)
        else:
            keystore_path.unlink()
        logger.info(f"Successfully deleted account {name} from keystores")
        return 0
    except Exception as e:
        logger.error(f"Failed to delete account {name} from keystores: {str(e)}")
        return 1


def decrypt_key(
    name: str,
    password: str | None = None,
    password_file_path: Path | None = None,
    keystores_path: Path = DEFAULT_KEYSTORES_PATH,
    print_key: bool = False,
) -> HexBytes | None:
    keystore_path = keystores_path.joinpath(name)
    key = None
    if password_file_path:
        password_file_path = Path(password_file_path).expanduser().resolve()
    with open(keystore_path, "r") as f:
        keystore_json = f.read()
        if not password and not password_file_path:
            retries = 3
            while retries > 0:
                retries -= 1
                password = getpass.getpass(
                    f"Enter your password for keystore {keystore_path.stem}: "
                )
                if not password:
                    logger.error("Password cannot be empty. Please try again.")
                    continue
                try:
                    key: HexBytes = EthAccountsClass.decrypt(keystore_json, password)
                    break
                except Exception:
                    logger.error(f"Passwords do not match. {retries} left.")
        elif password:
            try:
                key: HexBytes = EthAccountsClass.decrypt(keystore_json, password)
            except Exception:
                logger.error("Passwords do not match.")
                return None
        elif password_file_path:
            with password_file_path.open("r") as fp:
                password = fp.read()
            try:
                key: HexBytes = EthAccountsClass.decrypt(keystore_json, password)
            except Exception:
                logger.error("Passwords do not match.")
                return None
    if print_key:
        logger.info(f"Private key: {key.to_0x_hex()}")
    else:
        logger.info(
            "Private key decrypted successfully. Rerun the command and use the '-p' flag to print it."
        )
    return key
