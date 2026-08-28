import { NextRequest, NextResponse } from "next/server";

// Opt-in HTTP Basic Auth for the whole app. A no-op unless both env vars
// are set, so local development stays unauthenticated; a deployed instance
// sets these to require credentials before this single-tenant, no-accounts
// tool is reachable at all.
const USERNAME = process.env.BASIC_AUTH_USERNAME;
const PASSWORD = process.env.BASIC_AUTH_PASSWORD;

function unauthorized() {
  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Reconciliation Tool"' },
  });
}

export function middleware(request: NextRequest) {
  if (!USERNAME || !PASSWORD) {
    return NextResponse.next();
  }

  const header = request.headers.get("authorization");
  if (!header || !header.startsWith("Basic ")) {
    return unauthorized();
  }

  const decoded = Buffer.from(header.slice("Basic ".length), "base64").toString("utf-8");
  const separatorIndex = decoded.indexOf(":");
  const user = separatorIndex === -1 ? decoded : decoded.slice(0, separatorIndex);
  const pass = separatorIndex === -1 ? "" : decoded.slice(separatorIndex + 1);

  if (user !== USERNAME || pass !== PASSWORD) {
    return unauthorized();
  }

  return NextResponse.next();
}

export const config = {
  // Everything except Next.js internals and static assets.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
