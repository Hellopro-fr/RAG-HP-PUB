// tests/helpers/fixture.js
import { mkdir, writeFile, rm } from 'fs/promises';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
export const FIXTURE_ROOT = join(__dirname, '..', 'fixtures');

/**
 * Build a synthetic job on disk.
 *
 * @param {string} jobId
 * @param {object} [opts]
 * @param {string} [opts.domain='example.com']
 * @param {string[]} [opts.successUrls=[]]                          - URLs for the main dataset
 * @param {Array<{url, error?, statusCode?, statusText?}>} [opts.errorUrls=[]]
 * @param {string[]} [opts.nfrUrls=[]]                              - URLs for the nfr-{domain} dataset
 * @param {Array<{url, method?, retryCount?, errorMessages?, handledAt?}>} [opts.queueFiles=[]]
 * @param {Array<{dir, name, body}>} [opts.rawFiles=[]]             - arbitrary files (for malformed-JSON tests)
 */
export async function setupFixture(jobId, opts = {}) {
  const {
    domain = 'example.com',
    successUrls = [],
    errorUrls = [],
    nfrUrls = [],
    queueFiles = [],
    rawFiles = [],
  } = opts;

  const jobRoot = join(FIXTURE_ROOT, jobId);
  await rm(jobRoot, { recursive: true, force: true });

  // success
  if (successUrls.length) {
    const dir = join(jobRoot, 'storage', 'datasets', domain);
    await mkdir(dir, { recursive: true });
    for (let i = 0; i < successUrls.length; i++) {
      await writeFile(join(dir, `${i}.json`), JSON.stringify({ url: successUrls[i] }));
    }
  }

  // error
  if (errorUrls.length) {
    const dir = join(jobRoot, 'storage', 'datasets', `error-${domain}`);
    await mkdir(dir, { recursive: true });
    for (let i = 0; i < errorUrls.length; i++) {
      const entry = errorUrls[i];
      const payload = { url: entry.url };
      if (entry.error) payload.errorMessages = [entry.error];
      if (entry.statusCode !== undefined) payload.statusCode = entry.statusCode;
      if (entry.statusText) payload.statusText = entry.statusText;
      await writeFile(join(dir, `${i}.json`), JSON.stringify(payload));
    }
  }

  // nfr
  if (nfrUrls.length) {
    const dir = join(jobRoot, 'storage', 'datasets', `nfr-${domain}`);
    await mkdir(dir, { recursive: true });
    for (let i = 0; i < nfrUrls.length; i++) {
      await writeFile(join(dir, `${i}.json`), JSON.stringify({ url: nfrUrls[i] }));
    }
  }

  // queue files
  if (queueFiles.length) {
    const dir = join(jobRoot, 'storage', 'request_queues', domain);
    await mkdir(dir, { recursive: true });
    for (let i = 0; i < queueFiles.length; i++) {
      await writeFile(join(dir, `${i}.json`), JSON.stringify(queueFiles[i]));
    }
  }

  // raw files (opts out of JSON wrapping - for malformed-JSON tests)
  for (const r of rawFiles) {
    const dir = join(jobRoot, r.dir);
    await mkdir(dir, { recursive: true });
    await writeFile(join(dir, r.name), r.body);
  }

  return jobRoot;
}

export async function teardownFixture(jobId) {
  await rm(join(FIXTURE_ROOT, jobId), { recursive: true, force: true });
}
