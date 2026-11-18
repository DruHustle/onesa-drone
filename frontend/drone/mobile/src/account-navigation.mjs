// Enrollment is an external Account handoff, not a Drone sign-in or grant.
export const accountHome = "https://account.onesa.eu/account";
export const registeredReturn = "onesadrone://account/registered";

export function enrollmentUrl(tier, platform) {
  if (!["user", "admin"].includes(tier) || !["ios", "android"].includes(platform)) {
    throw new RangeError("Unsupported Onesa enrollment destination");
  }
  return "https://account.onesa.eu/register?audience=" + tier +
    "&product=drone&platform=" + platform;
}

// Accept only the exact application callback. Never parse a token, code, state,
// product, or privileged role out of an untrusted OS deep link.
export function isEnrollmentReturn(value) {
  return value === registeredReturn;
}
