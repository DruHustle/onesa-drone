// Independent cookie jar for the member whose access the administrator changes.
async function openOperator(request, fixture, assert) {
  const session = await request.newContext({ ignoreHTTPSErrors: true });
  const origin = { Origin: fixture.drone };
  const started = await session.post(
    fixture.drone + "/api/v1/auth/identity/start",
    { headers: origin, data: { reauthenticate: false } },
  );
  assert.equal(started.status(), 200);
  const authorization = new URL((await started.json()).authorization_url);
  assert.equal(authorization.origin, fixture.portal);
  const authorized = await session.get(authorization.href, { maxRedirects: 0 });
  assert.equal(authorized.status(), 303);
  const signIn = new URL(authorized.headers().location);
  assert.equal(signIn.origin, fixture.portal);
  assert.match(signIn.pathname, /^\/account\/sign-in\/[A-Za-z0-9_-]+$/);
  const interaction =
    fixture.portal +
    "/api/v1/account/interaction/" +
    signIn.pathname.split("/").pop();
  const details = await session.get(interaction);
  assert.equal(details.status(), 200);
  const login = await session.post(interaction + "/login", {
    headers: { Origin: fixture.portal },
    data: {
      email: "member@example.test",
      password: fixture.password,
      code: "",
      csrf: (await details.json()).csrf,
    },
  });
  assert.equal(login.status(), 200);
  const continuation = new URL(
    (await login.json()).continuePath,
    fixture.portal,
  );
  assert.equal(continuation.origin, fixture.portal);
  const complete = await session.get(continuation.href, { maxRedirects: 0 });
  assert.equal(complete.status(), 303);
  const callback = new URL(complete.headers().location);
  assert.equal(callback.origin, fixture.drone);
  assert.equal(callback.pathname, "/api/v1/auth/identity/callback");
  assert.equal(
    (await session.get(callback.href, { maxRedirects: 0 })).status(),
    303,
  );
  const response = await session.get(fixture.drone + "/api/v1/auth/me");
  assert.equal(response.status(), 200);
  const account = await response.json();
  assert.equal(account.identity_subject, fixture.member);
  assert.equal(account.role, "operator");
  assert.equal(account.tenant_id, fixture.tenant);
  return {
    session,
    headers: { Origin: fixture.drone, "X-CSRF-Token": account.csrf },
  };
}

module.exports = async function verifyMemberStatus({
  page,
  request,
  expect,
  assert,
  fixture,
  progress,
}) {
  progress("establish current member grant");
  const current = await openOperator(request, fixture, assert);
  let restored;
  try {
    const me = fixture.drone + "/api/v1/auth/me";
    progress("find member in Portal administration");
    await page.goto(fixture.portal + "/account");
    progress("fill Portal member search");
    await page.getByLabel("Find an account").fill("member@example.test");
    progress("submit Portal member search");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    const editor = page.locator("details").filter({
      has: page.locator("summary").filter({ hasText: "member@example.test" }),
    });
    progress("open returned Portal member row");
    await editor.locator("summary").click();
    const group = editor.getByRole("group", {
      name: "Member account",
      exact: true,
    });
    for (const action of ["Disable", "Restore"]) {
      progress(action + " Portal member");
      await group
        .getByLabel("Your password", { exact: true })
        .fill(fixture.password);
      await group
        .getByLabel("Your authenticator code", { exact: true })
        .fill(fixture.codes.shift());
      const saved = page.waitForResponse(
        (response) =>
          response.request().method() === "PUT" &&
          new URL(response.url()).pathname ===
            "/api/v1/admin/identity/accounts/" +
              fixture.member +
              "/member-status",
      );
      await group
        .getByRole("button", { name: action + " member account", exact: true })
        .click();
      assert.equal((await saved).status(), 200);
      await expect(
        group.getByRole("button", {
          name:
            (action === "Disable" ? "Restore" : "Disable") + " member account",
          exact: true,
        }),
      ).toBeVisible();
      assert.equal((await current.session.get(me)).status(), 401);
      if (action === "Disable") {
        const denied = await current.session.post(
          fixture.portal + "/api/v1/account/login",
          {
            headers: { Origin: fixture.portal },
            data: {
              email: "member@example.test",
              password: fixture.password,
              code: "",
            },
          },
        );
        assert.equal(denied.status(), 401);
      }
    }
    progress("verify fresh restored member authority");
    restored = await openOperator(request, fixture, assert);
    const forbidden = await restored.session.post(
      fixture.drone + "/api/v1/auth/workspace",
      { headers: restored.headers, data: { tenant_id: fixture.other } },
    );
    assert.equal(forbidden.status(), 403);
  } finally {
    await current.session.dispose();
    if (restored) await restored.session.dispose();
  }
};
