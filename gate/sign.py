"""Sign and verify records with SSH keys, through ssh-keygen.

Every record has a namespace, so a signature for one kind of record never
verifies as another kind: a pass record cannot pose as an approval.

The machine key is Tollgate's own key, in key_dir(). An approval is signed with
your SSH key instead. Verification always reads the allowed keys from the
settings on main, never from the change under check.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from gate import state

NAMESPACES = ("tollgate-lock", "tollgate-plan", "tollgate-pass", "tollgate-approval")
IDENTITY = "tollgate"


class SignError(RuntimeError):
    """A record could not be signed or does not verify. The message says why."""


def _run(args, data: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, input=data, capture_output=True, check=False)


def machine_key() -> Path:
    """This machine's private key. ensure_key() creates it."""
    return state.key_dir() / "id_ed25519"


def ensure_key() -> str:
    """Create this machine's key if it is missing. Return its public key line."""
    key = machine_key()
    if not key.exists():
        key.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(key.parent, 0o700)
        done = _run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "tollgate",
                     "-f", str(key)])
        if done.returncode:
            raise SignError(f"ssh-keygen could not make a key: {done.stderr.decode().strip()}")
    return Path(f"{key}.pub").read_text().strip()


def sign(data: bytes, namespace: str, key: str | None = None) -> bytes:
    """Return the signature of data. key is a private key file; the default is the machine key."""
    if namespace not in NAMESPACES:
        raise SignError(f"unknown namespace: {namespace}")
    key = key or str(machine_key())
    done = _run(["ssh-keygen", "-Y", "sign", "-q", "-n", namespace, "-f", key], data)
    if done.returncode:
        raise SignError(f"ssh-keygen could not sign: {done.stderr.decode().strip()}")
    return done.stdout


def verify(data: bytes, signature: bytes, namespace: str, signers: list) -> bool:
    """True when one of the public keys in signers signed data in this namespace."""
    if namespace not in NAMESPACES or not signers or not signature:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        allowed = Path(tmp, "allowed")
        allowed.write_text("".join(f'{IDENTITY} namespaces="{namespace}" {k.strip()}\n'
                                   for k in signers))
        sig = Path(tmp, "sig")
        sig.write_bytes(signature)
        done = _run(["ssh-keygen", "-Y", "verify", "-f", str(allowed), "-I", IDENTITY,
                     "-n", namespace, "-s", str(sig)], data)
        return done.returncode == 0


def write(path: Path, record: dict, namespace: str, key: str | None = None) -> None:
    """Write record to path and its signature to path.sig."""
    data = state.dumps(record)
    path.write_bytes(data)
    Path(f"{path}.sig").write_bytes(sign(data, namespace, key))


def read(path: Path, namespace: str, signers: list) -> dict:
    """Return the record at path. Raise SignError when it is missing or does not verify."""
    import json
    sig = Path(f"{path}.sig")
    if not path.exists() or not sig.exists():
        raise SignError(f"{path.name} is missing or not signed")
    data = path.read_bytes()
    if not verify(data, sig.read_bytes(), namespace, signers):
        raise SignError(f"{path.name} is not signed by a key in signers")
    return json.loads(data)
