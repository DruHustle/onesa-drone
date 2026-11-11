"""Product-local custody for the central Onesa account; no shared cookies or passwords."""

import secrets
import time
from dataclasses import dataclass
from sqlalchemy import Column, Float, String, Text, delete, select, func
from sqlalchemy.orm import declarative_base
from fastapi import HTTPException
from cryptography.fernet import Fernet, InvalidToken

from . import onesa_identity as protocol
from .models import Tenant
from .security import digest

IdentityBase = declarative_base()
TRANSACTION_SECONDS = 300
TRANSACTION_COOKIE = "drone_identity_transaction"
TRANSACTION_COOKIE_PATH = "/api/v1/auth/identity"


class IdentityTransaction(IdentityBase):
    __tablename__ = "identity_transactions"
    state_hash = Column(String, primary_key=True)
    browser_hash = Column(String, nullable=False)
    nonce = Column(String, nullable=False)
    encrypted_verifier = Column(Text, nullable=False)
    expires = Column(Float, nullable=False)
    subject = Column(String, nullable=True)
    tenant_id = Column(String, nullable=True)
    session_hash = Column(String, nullable=True)
    session_csrf = Column(String, nullable=True)
    retire_session_hash = Column(String, nullable=True)


class IdentitySession(IdentityBase):
    __tablename__ = "identity_sessions"
    token_hash = Column(String, primary_key=True)
    issuer = Column(String, nullable=False)
    subject = Column(String, nullable=False, index=True)
    encrypted_token = Column(Text, nullable=False)
    csrf = Column(String, nullable=False)
    expires = Column(Float, nullable=False)
    tenant_id = Column(String, nullable=True)


@dataclass(frozen=True)
class PendingSignIn:
    state: str
    browser: str
    nonce: str
    verifier: str


class IdentityService:
    def __init__(self, cfg, store):
        self.cfg, self.store = cfg, store
        self.cipher = Fernet(cfg.identity_encryption_key.encode("ascii"))
        self.config = protocol.IdentityConfig(
            issuer=cfg.identity_issuer,
            client_id=cfg.identity_client_id,
            client_secret=cfg.identity_client_secret,
            redirect_uri=cfg.identity_callback,
            product="drone",
            allow_local_http=cfg.origin.startswith(("http://127.0.0.1:", "http://localhost:")),
        )

    def encrypt(self, value):
        return self.cipher.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value):
        try:
            return self.cipher.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeError):
            raise protocol.IdentityError(
                "identity_rejected", "Your Onesa session is no longer valid"
            ) from None

    def begin(self, previous=None, previous_token="", *, mobile=False):
        state, nonce, verifier = protocol.new_transaction()
        if mobile:
            state = "mobile_" + state
        browser = secrets.token_urlsafe(32)
        with self.store.transaction() as db:
            db.execute(delete(IdentityTransaction).where(IdentityTransaction.expires <= time.time()))
            if db.scalar(select(func.count()).select_from(IdentityTransaction)) >= 2048:
                raise HTTPException(429, "Too many sign-in attempts; try again shortly")
            old = db.get(IdentitySession, digest(previous_token)) if previous_token else None
            db.add(
                IdentityTransaction(
                    state_hash=digest(state),
                    browser_hash=digest(browser),
                    nonce=nonce,
                    encrypted_verifier=self.encrypt(verifier),
                    expires=time.time() + TRANSACTION_SECONDS,
                    subject=previous.get("identity_subject") if previous else None,
                    tenant_id=previous.get("tenant_id") if previous else None,
                    session_hash=previous.get("_session_hash") if previous else None,
                    session_csrf=previous.get("csrf") if previous else None,
                    retire_session_hash=(
                        old.token_hash if old and old.issuer == self.config.issuer else None
                    ),
                )
            )
        return PendingSignIn(state, browser, nonce, verifier)

    def consume(self, state, browser):
        if not state or len(state) > 128 or not browser or len(browser) > 128:
            raise protocol.IdentityError(
                "identity_callback_invalid", "Sign-in has expired. Please start again"
            )
        with self.store.transaction() as db:
            row = db.scalar(
                select(IdentityTransaction)
                .where(IdentityTransaction.state_hash == digest(state))
                .with_for_update()
            )
            if (
                not row
                or row.expires <= time.time()
                or not secrets.compare_digest(row.browser_hash, digest(browser))
            ):
                raise protocol.IdentityError(
                    "identity_callback_invalid", "Sign-in has expired. Please start again"
                )
            db.delete(row)
            return row

    def create_session(self, identity, identity_token, pending, *, mobile=False):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        if mobile:
            token = "mobile_" + token
        choices = self.workspaces(identity)
        permitted = {item["id"] for item in choices}
        # An existing explicit choice survives reauthentication. A single normal
        # membership is unambiguous. Global administrators always choose a workspace.
        selected = pending.tenant_id if pending.tenant_id in permitted else None
        if selected is None and not identity.global_admin and len(choices) == 1:
            selected = choices[0]["id"]
        expires = min(identity.expires_at, time.time() + self.cfg.session_seconds)
        with self.store.transaction() as db:
            if pending.session_hash:
                # Reauthentication confirms an existing browser session. It must
                # not recreate one that was signed out or changed while the
                # user was at the account provider, including during its reply.
                previous = db.scalar(
                    select(IdentitySession)
                    .where(IdentitySession.token_hash == pending.session_hash)
                    .with_for_update()
                )
                if (
                    not previous
                    or previous.expires <= time.time()
                    or previous.issuer != identity.issuer
                    or previous.subject != identity.subject
                    or previous.csrf != pending.session_csrf
                    or previous.tenant_id != pending.tenant_id
                ):
                    raise protocol.IdentityError(
                        "identity_reauthentication_expired", "Your session changed. Sign in again"
                    )
                db.delete(previous)
            elif pending.retire_session_hash:
                # The Strict session cookie may be absent on a cross-site
                # callback. Retire the prior browser session captured at start,
                # including when ordinary sign-in switches to another account.
                db.execute(
                    delete(IdentitySession).where(
                        IdentitySession.token_hash == pending.retire_session_hash,
                        IdentitySession.issuer == self.config.issuer,
                    )
                )
            db.execute(delete(IdentitySession).where(IdentitySession.expires <= time.time()))
            for old in db.scalars(
                select(IdentitySession)
                .where(
                    IdentitySession.issuer == identity.issuer,
                    IdentitySession.subject == identity.subject,
                )
                .order_by(IdentitySession.expires.desc())
                .offset(4)
            ):
                db.delete(old)
            db.add(
                IdentitySession(
                    token_hash=digest(token),
                    issuer=identity.issuer,
                    subject=identity.subject,
                    encrypted_token=self.encrypt(identity_token),
                    csrf=csrf,
                    expires=expires,
                    tenant_id=selected,
                )
            )
        return token, int(expires - time.time())

    def authenticate(self, token):
        with self.store.session() as db:
            row = db.get(IdentitySession, digest(token)) if token else None
            if not row or row.expires <= time.time() or row.issuer != self.config.issuer:
                raise HTTPException(401, "Sign in with your Onesa account")
        identity = protocol.validate_session(self.config, self.decrypt(row.encrypted_token))
        if identity.subject != row.subject:
            raise protocol.IdentityError("identity_rejected", "Your Onesa session is no longer valid")
        # The issuer request may overlap local logout, expiry or a workspace
        # switch. Never authorize from the detached pre-request session alone.
        with self.store.session() as db:
            current = db.get(IdentitySession, row.token_hash)
            if (
                not current
                or current.expires <= time.time()
                or current.issuer != row.issuer
                or current.subject != row.subject
                or current.csrf != row.csrf
                or current.tenant_id != row.tenant_id
                or current.encrypted_token != row.encrypted_token
            ):
                raise HTTPException(401, "Your Onesa session changed; sign in again")
        roles = self.membership_roles(identity)
        role = "admin" if identity.global_admin else roles.get(row.tenant_id, "viewer")
        if row.tenant_id:
            with self.store.session() as db:
                exists = db.get(Tenant, row.tenant_id) is not None
            if not exists or (not identity.global_admin and row.tenant_id not in roles):
                raise HTTPException(403, "Workspace access has changed; sign in again")
        return {
            "id": "identity:" + identity.subject,
            "email": identity.email,
            "name": identity.name,
            "role": role,
            "tenant_id": row.tenant_id,
            "csrf": row.csrf,
            "expires": min(row.expires, identity.expires_at),
            "identity_subject": identity.subject,
            "global_admin": identity.global_admin,
            "identity_managed": True,
            "account_url": self.config.issuer.removesuffix("/api/v1/identity") + "/account",
            "access_url": self.config.issuer.removesuffix("/api/v1/identity") + "/account?tab=access",
            "_identity": identity,
            "_session_hash": row.token_hash,
        }

    @staticmethod
    def membership_roles(identity):
        result = {}
        ranks = {"viewer": 0, "operator": 1, "admin": 2}
        ceiling = identity.product_roles.get("drone", "viewer")
        for item in identity.memberships:
            if item["product"] == "drone":
                if item["tenant_id"] in result:
                    raise protocol.IdentityError(
                        "identity_unavailable", "Onesa workspace access is invalid", 503
                    )
                # Product access is the maximum role for the application;
                # membership may further narrow it for an individual tenant.
                result[item["tenant_id"]] = min((ceiling, item["role"]), key=ranks.__getitem__)
        return result

    def workspaces(self, identity):
        roles = self.membership_roles(identity)
        with self.store.session() as db:
            query = select(Tenant).order_by(Tenant.name, Tenant.id)
            if not identity.global_admin:
                query = query.where(Tenant.id.in_(roles))
            rows = list(db.scalars(query.limit(1000)))
            return [
                {"id": row.id, "name": row.name, "role": "admin" if identity.global_admin else roles[row.id]}
                for row in rows
            ]

    @staticmethod
    def require_fresh(identity):
        if not identity.fresh(mfa=True):
            raise protocol.IdentityError(
                "identity_reauthentication_required", "Confirm your Onesa account with MFA to continue", 403
            )


def public_account(account):
    return {key: value for key, value in account.items() if not key.startswith("_")}
