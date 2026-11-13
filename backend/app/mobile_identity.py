"""System-browser sign-in for the native offline planner and bench notebook."""
import re
import time
from urllib.parse import urlencode

from fastapi import Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from . import onesa_identity as protocol
from .identity import IdentitySession, IdentityTransaction
from .security import digest


class MobileExchange(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    state: str = Field(pattern=r"^mobile_[a-zA-Z0-9_-]{43}$")
    proof: str = Field(pattern=r"^[a-zA-Z0-9_-]{43}$")
    code: str = Field(min_length=1, max_length=4096)


def is_mobile_state(state):
    return bool(re.fullmatch(r"mobile_[a-zA-Z0-9_-]{43}", state))


def mobile_callback(service, state, code, error):
    # The external browser never obtains the proof returned to the native client.
    # Route only live app-initiated transactions to the fixed registered scheme.
    with service.store.session() as db:
        tx = db.get(IdentityTransaction, digest(state))
        if not tx or tx.expires <= time.time():
            raise protocol.IdentityError("identity_callback_invalid", "Sign-in expired. Start again")
    if error or not code or len(code) > 4096:
        params = {"state": state, "error": "identity_cancelled"}
    else:
        params = {"state": state, "code": code}
    return RedirectResponse("onesadrone://account/callback?" + urlencode(params), status_code=303)


def install_mobile_identity(app, service, limiter):
    def enabled():
        if not service:
            raise HTTPException(404, "Drone shared sign-in is unavailable")

    def session_key(authorization):
        enabled()
        match = re.fullmatch(r"Bearer (mobile_[A-Za-z0-9_-]{43})", authorization)
        if not match:
            raise HTTPException(401, "Sign in with Onesa")
        return match[1]

    @app.post("/api/v1/auth/mobile/start")
    def mobile_start(request: Request):
        enabled()
        limiter.check("identity-login:" + (request.client.host if request.client else "unknown"), 12)
        pending = service.begin(mobile=True)
        return {
            "state": pending.state,
            "proof": pending.browser,
            "authorization_url": protocol.authorization_url(
                service.config, pending.state, pending.nonce, pending.verifier
            ),
        }

    @app.post("/api/v1/auth/mobile/exchange")
    def mobile_exchange(data: MobileExchange):
        enabled()
        pending = service.consume(data.state, data.proof)
        grant = protocol.exchange_code(service.config, data.code, service.decrypt(pending.encrypted_verifier))
        try:
            identity = protocol.validate_session(service.config, grant)
            credential, _ = service.create_session(identity, grant, pending, mobile=True)
        except Exception:
            try:
                protocol.revoke_session(service.config, grant)
            except protocol.IdentityError:
                pass
            raise
        return {"session": credential}

    @app.get("/api/v1/auth/mobile/account")
    def mobile_account(authorization: str = Header(default="")):
        token = session_key(authorization)
        account = service.authenticate(token)
        identity = account["_identity"]
        return {
            "name": identity.name,
            "email": identity.email,
            "storage_scope": digest(identity.issuer + "\x00" + identity.subject),
            "global_admin": identity.global_admin,
            "workspaces": service.workspaces(identity),
        }

    @app.post("/api/v1/auth/mobile/logout")
    def mobile_logout(authorization: str = Header(default="")):
        token = session_key(authorization)
        with service.store.transaction() as db:
            row = db.get(IdentitySession, digest(token), with_for_update=True)
            encrypted = row.encrypted_token if row else None
            if row:
                db.delete(row)
        revoked = False
        if encrypted:
            try:
                revoked = protocol.revoke_session(service.config, service.decrypt(encrypted), all_sessions=True)
            except protocol.IdentityError:
                pass
        return {"local_signed_out": True, "central_signed_out": revoked}
