/**
 * Routes Express `/api/albums/*` — proxy fin vers `image-download-service`.
 *
 * Le parent monte ce routeur derrière `authenticateToken` :
 *   app.use('/api/albums', authenticateToken, mountAlbumsRouter({ auditMiddleware }));
 *
 * Chaque route POST/DELETE est :
 *   1. Wrappée par `auditMiddleware('action_name', { captureParams: [...] })`.
 *   2. Limitée par un `express-rate-limit` (10/min/user, configurable).
 *
 * Les GET ne sont ni audités ni rate-limités (lecture seule, peut être appelé
 * souvent par React Query background refetch).
 *
 * @param {object} opts
 * @param {function} opts.auditMiddleware - factory `(action, options) => middleware`
 * @param {function} [opts.fetchFn]        - injection pour tests (default: global fetch)
 * @param {string}   [opts.baseUrl]        - URL du Python service (default: env var)
 * @param {number}   [opts.destructiveLimit] - max destructive calls/min/user (default: 10)
 * @returns {import('express').Router}
 */

import { Router } from 'express';
import rateLimit from 'express-rate-limit';
import { proxyToImageDownload } from './imageDownloadProxy.js';

export function mountAlbumsRouter({
  auditMiddleware,
  fetchFn,
  baseUrl,
  destructiveLimit,
} = {}) {
  if (typeof auditMiddleware !== 'function') {
    throw new Error('mountAlbumsRouter: auditMiddleware factory is required');
  }

  const router = Router();

  const limit = Number.isFinite(destructiveLimit)
    ? destructiveLimit
    : parseInt(process.env.ALBUMS_DESTRUCTIVE_LIMIT || '10', 10);

  // Rate-limit destructif : 10 / minute / utilisateur (clé = role JWT, fallback IP).
  // En cas de pénurie de role (token mal formé), on retombe sur IP — req.ip est
  // fiable car `app.set('trust proxy', N)` est posé dans server.js.
  const destructiveLimiter = rateLimit({
    windowMs: 60 * 1000,
    max: limit,
    standardHeaders: true,
    legacyHeaders: false,
    keyGenerator: (req) => {
      const role = req.user && req.user.role;
      return role ? `albums:role:${role}` : `albums:ip:${req.ip}`;
    },
  });

  // Helper pour générer le forward d'un appel proxy.
  const fwd = (method, pathBuilder) => async (req, res) => {
    const path = pathBuilder(req);
    return proxyToImageDownload(req, res, { method, path, fetchFn, baseUrl });
  };

  // ---------------------------------------------------------------------------
  // GET (lecture, pas d'audit, pas de rate-limit destructif)
  // ---------------------------------------------------------------------------

  router.get('/', fwd('GET', () => '/domains/_summary'));

  router.get('/jobs/:jobId', fwd('GET', (req) => `/jobs/${encodeURIComponent(req.params.jobId)}`));

  router.get(
    '/:domain/errors',
    fwd('GET', (req) => `/sync/${encodeURIComponent(req.params.domain)}/errors`),
  );

  router.get(
    '/:domain/products',
    fwd('GET', (req) => `/domains/${encodeURIComponent(req.params.domain)}/products`),
  );

  // ---------------------------------------------------------------------------
  // POST (audit + rate-limit)
  // ---------------------------------------------------------------------------

  router.post(
    '/:domain/sync',
    destructiveLimiter,
    auditMiddleware('sync_album', { captureParams: ['domain'] }),
    fwd('POST', (req) => `/sync/${encodeURIComponent(req.params.domain)}`),
  );

  router.post(
    '/:domain/products/:id/redownload',
    destructiveLimiter,
    auditMiddleware('redownload_product', { captureParams: ['domain', 'id'] }),
    fwd(
      'POST',
      (req) => `/products/${encodeURIComponent(req.params.domain)}/${encodeURIComponent(req.params.id)}/redownload`,
    ),
  );

  router.post(
    '/:domain/products/:id/images/:filename/redownload',
    destructiveLimiter,
    auditMiddleware('redownload_image', { captureParams: ['domain', 'id', 'filename'] }),
    fwd(
      'POST',
      (req) =>
        `/images/${encodeURIComponent(req.params.domain)}/${encodeURIComponent(req.params.id)}/${encodeURIComponent(req.params.filename)}/redownload`,
    ),
  );

  // ---------------------------------------------------------------------------
  // DELETE (audit + rate-limit)
  // ---------------------------------------------------------------------------

  router.delete(
    '/:domain',
    destructiveLimiter,
    auditMiddleware('delete_album', { captureParams: ['domain'] }),
    fwd('DELETE', (req) => `/domains/${encodeURIComponent(req.params.domain)}`),
  );

  router.delete(
    '/:domain/products/:id',
    destructiveLimiter,
    auditMiddleware('delete_product', { captureParams: ['domain', 'id'] }),
    fwd(
      'DELETE',
      (req) => `/products/${encodeURIComponent(req.params.domain)}/${encodeURIComponent(req.params.id)}`,
    ),
  );

  router.delete(
    '/:domain/products/:id/images/:filename',
    destructiveLimiter,
    auditMiddleware('delete_image', { captureParams: ['domain', 'id', 'filename'] }),
    fwd(
      'DELETE',
      (req) =>
        `/images/${encodeURIComponent(req.params.domain)}/${encodeURIComponent(req.params.id)}/${encodeURIComponent(req.params.filename)}`,
    ),
  );

  return router;
}
