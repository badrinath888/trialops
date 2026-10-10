import hashlib, hmac, secrets
from fastapi import HTTPException, Request
from db import one, secret


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(value):
    salt = secrets.token_hex(16)
    return (
        salt
        + ":"
        + hashlib.pbkdf2_hmac(
            "sha256", value.encode(), bytes.fromhex(salt), 600000
        ).hex()
    )


def password_ok(value, stored):
    try:
        salt, expected = stored.split(":")
        actual = hashlib.pbkdf2_hmac(
            "sha256", value.encode(), bytes.fromhex(salt), 600000
        ).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, AttributeError):
        return False


def actor(request: Request):
    row = one(
        """SELECT u.id AS user_id,u.name,u.email,u.guest,u.email_verified_at,s.workspace_id,m.role,w.name AS workspace_name,w.demo
      FROM sessions s JOIN users u ON u.id=s.user_id JOIN workspaces w ON w.id=s.workspace_id
      JOIN memberships m ON m.workspace_id=s.workspace_id AND m.user_id=s.user_id
      WHERE s.token_hash=%s AND s.expires_at>now() AND (w.expires_at IS NULL OR w.expires_at>now())""",
        (digest(request.cookies.get("trialops_session", "")),),
    )
    if not row:
        raise HTTPException(
            401, "Your session expired. Sign in or start a new sample workspace."
        )
    rate("session:" + str(row["user_id"]), 180, 60)
    return row


def require(a, roles=("owner", "reviewer")):
    if a["role"] not in roles:
        raise HTTPException(403, "Your workspace role does not permit this action.")


def rate(key, maximum, seconds=3600):
    row = one(
        """INSERT INTO rate_limits(key) VALUES (%s)
      ON CONFLICT(key) DO UPDATE SET
      count=CASE WHEN rate_limits.window_start<now()-(%s * interval '1 second') THEN 1 ELSE rate_limits.count+1 END,
      window_start=CASE WHEN rate_limits.window_start<now()-(%s * interval '1 second') THEN now() ELSE rate_limits.window_start END
      RETURNING count""",
        (digest(key), seconds, seconds),
    )
    if row["count"] > maximum:
        raise HTTPException(429, "Request limit reached. Please wait and try again.")
