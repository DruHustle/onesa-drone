// Establish browser access without forwarding a project secret through redirects.
export async function installAutomationSession(context, origin, secret) {
  if (!secret) return;
  const response = await context.request.get(origin, {
    headers: {
      "x-vercel-protection-bypass": secret,
      "x-vercel-set-bypass-cookie": "true",
    },
    maxRedirects: 0,
  });
  const status = response.status();
  if (![200, 302, 303, 307, 308].includes(status))
    throw Error("Approved automation access was refused");
  const location = response.headers().location;
  if (location) assertFixtureOrigin(new URL(location, origin).href, origin);
  const cookies = await context.cookies();
  const cookie = cookies.find(
    (item) => item.name === "_vercel_jwt" && item.secure,
  );
  await context.clearCookies();
  if (!cookie)
    throw Error("Protected deployment did not establish an automation session");
  // Rebind the returned cookie to this exact host; never inherit a parent domain.
  await context.addCookies([
    {
      name: cookie.name,
      value: cookie.value,
      url: origin,
      secure: true,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
}

export function assertFixtureOrigin(url, origin) {
  if (new URL(url).origin !== origin)
    throw Error(
      "Protected deployment redirected outside the fixture origin; approved automation access is required before entering credentials",
    );
}
