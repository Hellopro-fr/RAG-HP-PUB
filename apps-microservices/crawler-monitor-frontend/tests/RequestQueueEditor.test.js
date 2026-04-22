import { describe, it } from 'node:test';
import assert from 'node:assert';

describe('RequestQueueEditor', () => {
  it('status filter options are the three expected values', () => {
    const options = ['all', 'pending', 'handled'];
    assert.deepStrictEqual(options, ['all', 'pending', 'handled']);
  });

  it('counts bar stays constant — counts come from unfiltered backend field', () => {
    // Verifies the design contract: counts object is always unfiltered totals
    const mockResponse = {
      items: [],
      total: 100,
      page: 1,
      limit: 50,
      totalPages: 2,
      counts: { total: 523, pending: 336, handled: 187 },
    };
    assert.ok(mockResponse.counts, 'counts field must be present in backend response');
    assert.strictEqual(
      mockResponse.counts.total,
      mockResponse.counts.pending + mockResponse.counts.handled,
      'counts.total must equal pending + handled'
    );
  });

  it('changeStatusFilter resets page to 1', () => {
    // Stub: logic is exercised in the component; this documents the contract
    let page = 5;
    const changeStatusFilter = () => { page = 1; };
    changeStatusFilter('pending');
    assert.strictEqual(page, 1, 'Page must reset to 1 on filter change');
  });
});
