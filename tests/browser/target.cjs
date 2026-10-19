// Mutating browser tests may only target the isolated 3002 test stack; live (3001) and demo (3003) are rejected before any request.
module.exports = () => {
  const raw = process.env.TEST_WEB_URL || 'http://localhost:3002'; let u;
  try { u = new URL(raw); } catch { console.error('TEST_WEB_URL is not a valid URL.'); process.exit(2); }
  if (!['localhost', '127.0.0.1'].includes(u.hostname) || u.port !== '3002') { console.error('Refusing to run browser tests against ' + u.origin + ': only http://localhost:3002 (test stack) is allowed. 3001 is live, 3003 is demo.'); process.exit(2); }
  return u.origin;
};
