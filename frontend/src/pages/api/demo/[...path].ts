import type { APIRoute } from 'astro';

// Server-side passthrough to the gateway's /demo routes, so the browser never talks to the gateway directly.
export const ALL: APIRoute = async({ params, request }) => {
  const base = process.env.GATEWAY_URL ?? 'http://localhost:8082';
  const upstream = await fetch(`${base}/demo/${params.path}`, {
    method: request.method,
    headers: { 'content-type': 'application/json' },
    body: request.method === 'GET' ? undefined : await request.text(),
  });
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { 'content-type': 'application/json' },
  });
};
