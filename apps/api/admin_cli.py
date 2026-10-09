"""Local operator administration. Never exposed as an HTTP endpoint."""

import argparse, getpass, json
from uuid import UUID
from db import connect, query
from security import password_hash

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "command", choices=["workspaces", "feedback", "delete-workspace", "reset-password"]
)
parser.add_argument("--workspace")
parser.add_argument("--email")
args = parser.parse_args()
if args.command == "workspaces":
    print(
        json.dumps(
            query(
                "SELECT id,name,demo,created_at,expires_at FROM workspaces ORDER BY created_at DESC"
            ),
            default=str,
            indent=2,
        )
    )
elif args.command == "feedback":
    print(
        json.dumps(
            query(
                "SELECT f.id,f.workspace_id,f.rating,f.message,f.created_at FROM feedback f ORDER BY f.created_at DESC LIMIT 1000"
            ),
            default=str,
            indent=2,
        )
    )
elif args.command == "delete-workspace":
    wid = UUID(args.workspace or "")
    confirmation = input(
        f"This permanently removes workspace {wid}. Type the complete UUID to confirm: "
    )
    if confirmation != str(wid):
        raise SystemExit("Cancelled")
    with connect() as c:
        c.execute("DELETE FROM feedback WHERE workspace_id=%s", (wid,))
        c.execute("DELETE FROM workspaces WHERE id=%s", (wid,))
        c.execute(
            "DELETE FROM users WHERE NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=users.id)"
        )
    print("Workspace removed. Existing backups retain their earlier contents.")
else:
    if not args.email:
        raise SystemExit("--email required")
    password = getpass.getpass("New password (12–128 characters): ")
    if not 12 <= len(password) <= 128:
        raise SystemExit("Invalid password length")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords differ")
    with connect() as c:
        user = c.execute(
            "UPDATE users SET password_hash=%s WHERE email=%s AND NOT guest RETURNING id",
            (password_hash(password), args.email.lower()),
        ).fetchone()
        if not user:
            raise SystemExit("Account not found")
        c.execute("DELETE FROM sessions WHERE user_id=%s", (user["id"],))
    print(
        "Password reset and existing sessions revoked. Verify the requester independently before sharing access."
    )
