"""Admin CLI.

    python -m backend.app.manage add-user <username> "<Display Name>" [--role staff|mp|admin]
    python -m backend.app.manage set-password <username>
    python -m backend.app.manage deactivate <username>
    python -m backend.app.manage list-users
    python -m backend.app.manage check-mapping
"""
from __future__ import annotations

import argparse
import getpass
import sys

from . import auth, db


def _password() -> str:
    pw = getpass.getpass("Password (10+ chars): ")
    if pw != getpass.getpass("Repeat: "):
        sys.exit("Passwords don't match")
    return pw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="manage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-user")
    a.add_argument("username")
    a.add_argument("display_name")
    a.add_argument("--role", default="staff", choices=("staff", "mp", "admin"))
    sp = sub.add_parser("set-password")
    sp.add_argument("username")
    d = sub.add_parser("deactivate")
    d.add_argument("username")
    sub.add_parser("list-users")
    sub.add_parser("check-mapping")
    args = ap.parse_args(argv)
    db.init_db()

    if args.cmd == "add-user":
        auth.create_user(args.username, args.display_name, _password(), args.role)
        print(f"Created {args.username} ({args.role})")
    elif args.cmd == "set-password":
        with db.get_conn() as conn:
            n = conn.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                             (auth.hash_password(_password()), args.username)).rowcount
            conn.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username = ?)",
                         (args.username,))
        print("Updated" if n else "No such user")
    elif args.cmd == "deactivate":
        with db.get_conn() as conn:
            n = conn.execute("UPDATE users SET active = 0 WHERE username = ?", (args.username,)).rowcount
            conn.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username = ?)",
                         (args.username,))
        print("Deactivated" if n else "No such user")
    elif args.cmd == "list-users":
        with db.get_conn() as conn:
            for r in conn.execute("SELECT username, display_name, role, active FROM users ORDER BY username"):
                print(f"{r['username']:<20} {r['display_name']:<30} {r['role']:<6} {'active' if r['active'] else 'inactive'}")
    elif args.cmd == "check-mapping":
        from .services import formmap
        problems = formmap.check_consistency()
        print("Mapping consistent with snapshot" if not problems else "\n".join(problems))
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
