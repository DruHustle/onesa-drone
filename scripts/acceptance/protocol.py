import json
import os
import secrets
import sys
from urllib.parse import urlsplit, parse_qs
import httpx

fixture = json.loads(os.environ["LOCAL_FIXTURE"])
drone_origin = fixture["drone"]
portal_origin = fixture["portal"]
native = os.environ.get("NATIVE") == "1"
tls = os.environ["FIXTURE_CA"]
step = ""


def check(condition, description):
    if not condition:
        raise RuntimeError(step + " " + description)


def expect(response, status):
    check(
        response.status_code == status,
        f"{response.request.method} {response.request.url.path.split('/')[:4]} expected {status}, got {response.status_code}",
    )
    return response


def run(role, evidence):
    global step
    with httpx.Client(verify=tls, timeout=10, trust_env=False) as client:
        for state in ["signed out", "active Portal"] + (["native"] if native else []):
            step = role + " / " + state
            mobile = state == "native"
            if mobile:
                start = expect(client.post(drone_origin + "/api/v1/auth/mobile/start"), 200).json()
            else:
                start = expect(
                    client.post(
                        drone_origin + "/api/v1/auth/identity/start",
                        headers={"Origin": drone_origin},
                        json={"reauthenticate": False},
                    ),
                    200,
                ).json()
            auth = expect(client.get(start["authorization_url"]), 303)
            location = auth.headers["location"]
            if location.startswith(drone_origin + "/api/v1/auth/identity/callback") and state != "signed out":
                resumed = auth
            else:
                check(
                    location.startswith(portal_origin + "/account/sign-in/"), "incorrect Portal destination"
                )
                uid = location.split("/")[-1]
                interaction = portal_origin + "/api/v1/account/interaction/" + uid
                details = expect(client.get(interaction), 200).json()
                if state == "signed out":
                    check(details["account"] is None, "expected signed-out interaction")
                    payload = {
                        "email": role + "@example.test",
                        "password": fixture["password"],
                        "csrf": details["csrf"],
                        "code": fixture["codes"].pop(0) if role == "admin" else "",
                    }
                    login = expect(
                        client.post(interaction + "/login", headers={"Origin": portal_origin}, json=payload),
                        200,
                    )
                else:
                    check(details["account"]["id"] == fixture[role], "active account missing")
                    login = expect(
                        client.post(
                            interaction + "/continue",
                            headers={"Origin": portal_origin},
                            json={"csrf": details["csrf"]},
                        ),
                        200,
                    )
                resumed = expect(client.get(portal_origin + login.json()["continuePath"]), 303)
            callback = expect(client.get(resumed.headers["location"]), 303)
            if mobile:
                loc = urlsplit(callback.headers["location"])
                check(loc.scheme == "onesadrone" and loc.path == "/callback", "expected native redirect")
                params = parse_qs(loc.query)
                check(params["state"] == [start["state"]], "unbound callback")
                session = expect(
                    client.post(
                        drone_origin + "/api/v1/auth/mobile/exchange",
                        json={"state": start["state"], "proof": start["proof"], "code": params["code"][0]},
                    ),
                    200,
                ).json()["session"]
                info = expect(
                    client.get(
                        drone_origin + "/api/v1/auth/mobile/account",
                        headers={"Authorization": "Bearer " + session},
                    ),
                    200,
                ).json()
                check(
                    info["email"] == role + "@example.test" and info["global_admin"] == (role == "admin"),
                    "native identity role",
                )
                expected_workspaces = {fixture["tenant"]: "operator"}
                if role == "admin":
                    expected_workspaces = {fixture["tenant"]: "admin", fixture["other"]: "admin"}
                check(
                    {row["id"]: row["role"] for row in info["workspaces"]} == expected_workspaces,
                    "native workspace grants",
                )
                mobile_headers = {"Authorization": "Bearer " + session}
                logout = expect(
                    client.post(drone_origin + "/api/v1/auth/mobile/logout", headers=mobile_headers), 200
                ).json()
                check(
                    logout == {"local_signed_out": True, "central_signed_out": True}, "native global logout"
                )
                expect(client.get(drone_origin + "/api/v1/auth/mobile/account", headers=mobile_headers), 401)
                expect(client.get(drone_origin + "/api/v1/auth/me"), 401)
                print(
                    "PASS "
                    + step
                    + " issuer + custom callback + authorized workspaces + global logout and invalidated web grant; device dispatch unobserved",
                    flush=True,
                )
                continue
            check(
                callback.headers["location"] == "/",
                "Drone callback did not return to the workspace",
            )
            me = expect(client.get(drone_origin + "/api/v1/auth/me"), 200).json()
            check(me["identity_subject"] == fixture[role], "stable subject mismatch")
            if role == "admin":
                expect(
                    client.post(
                        drone_origin + "/api/v1/auth/workspace",
                        json={"tenant_id": fixture["tenant"]},
                        headers={"Origin": drone_origin, "X-CSRF-Token": me["csrf"]},
                    ),
                    200,
                )
                me = expect(client.get(drone_origin + "/api/v1/auth/me"), 200).json()
            check(
                me["tenant_id"] == fixture["tenant"]
                and me["role"] == ("admin" if role == "admin" else "operator"),
                "role or workspace mismatch",
            )
            print("PASS " + step + " stable Portal subject, role and workspace", flush=True)
            headers = {"Origin": drone_origin, "X-CSRF-Token": me["csrf"]}
            if state == "active Portal":
                pref = expect(client.get(drone_origin + "/api/v1/settings"), 200).json()
                pref["currency"] = "GBP"
                expect(
                    client.put(drone_origin + "/api/v1/settings", headers=headers, json=pref),
                    200 if role == "admin" else 403,
                )
                if role == "admin":
                    foreign = expect(
                        client.post(
                            drone_origin + "/api/v1/auth/workspace",
                            headers=headers,
                            json={"tenant_id": fixture["other"]},
                        ),
                        200,
                    ).json()
                    foreign_headers = {
                        "Origin": drone_origin,
                        "X-CSRF-Token": foreign["csrf"],
                        "Idempotency-Key": secrets.token_urlsafe(16),
                    }
                    foreign_delivery = expect(
                        client.post(
                            drone_origin + "/api/v1/missions",
                            headers=foreign_headers,
                            json={
                                "label": "Other tenant fixture",
                                "origin": {"lat": 52.52, "lon": 13.405},
                                "destination": {"lat": 52.523, "lon": 13.411},
                                "package_weight": 1,
                                "package_kind": "standard",
                            },
                        ),
                        201,
                    ).json()
                    evidence["foreign_mission"] = foreign_delivery["mission"]["id"]
                    restored = expect(
                        client.post(
                            drone_origin + "/api/v1/auth/workspace",
                            headers=foreign_headers,
                            json={"tenant_id": fixture["tenant"]},
                        ),
                        200,
                    ).json()
                    headers["X-CSRF-Token"] = restored["csrf"]
                    check(
                        expect(client.get(drone_origin + "/api/v1/settings"), 200).json()["currency"]
                        == "GBP",
                        "admin write readback",
                    )
                    print("PASS admin preferences write + readback", flush=True)
                else:
                    expect(
                        client.post(
                            drone_origin + "/api/v1/missions",
                            headers=headers | {"Idempotency-Key": secrets.token_urlsafe(16)},
                            json={
                                "label": "Synthetic parcel",
                                "origin": {"lat": 52.52, "lon": 13.405},
                                "destination": {"lat": 52.523, "lon": 13.411},
                                "package_weight": 1,
                                "package_kind": "standard",
                            },
                        ),
                        201,
                    )
                    expect(
                        client.post(
                            drone_origin + "/api/v1/auth/workspace",
                            headers=headers,
                            json={"tenant_id": fixture["other"]},
                        ),
                        403,
                    )
                    expect(
                        client.get(
                            drone_origin + "/api/v1/missions/" + evidence["foreign_mission"] + "/history"
                        ),
                        404,
                    )
                    print(
                        "PASS normal delivery 201, administration 403, foreign workspace 403 and foreign mission history 404",
                        flush=True,
                    )
            if state == "signed out":
                client.cookies.delete("drone_session")
        if not native:
            expect(client.post(drone_origin + "/api/v1/auth/logout", headers=headers), 200)
        expect(client.get(drone_origin + "/api/v1/auth/me"), 401)
        print("PASS " + role + " global sign-out", flush=True)


try:
    evidence = {}
    for role in ["admin", "member"]:
        run(role, evidence)
except Exception as exc:
    print(
        "FAILED " + step + " " + (str(exc) if type(exc) is RuntimeError else type(exc).__name__), flush=True
    )
    sys.exit(1)
