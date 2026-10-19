import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Approval } from './api/workflows'
import { announce, approvalHref, headline } from './approvals.ts'

const approval = (id: number, extra: Partial<Approval> = {}): Approval => ({
  id,
  run_id: 10 + id,
  project_id: 1,
  project_name: 'Shop',
  workflow_id: 5,
  workflow_name: 'Listing',
  label: 'Approve listing',
  prompt: '',
  previous_label: 'Draft',
  previous: '',
  waiting_since: '2026-10-16T10:00:00Z',
  ...extra,
})

test('nothing new means nothing to announce', () => {
  assert.equal(announce(new Set(), []), null)
  assert.equal(announce(new Set([1, 2]), [approval(1), approval(2)]), null)
})

test('one new approval is announced by itself', () => {
  const result = announce(new Set([1]), [approval(1), approval(2)])
  assert.deepEqual(result, { kind: 'one', approval: approval(2) })
})

test('several new approvals make one announcement, not one each', () => {
  assert.deepEqual(announce(new Set([1]), [approval(1), approval(2), approval(3)]), { kind: 'many', count: 2 })
  assert.deepEqual(announce(new Set(), [approval(1), approval(2)]), { kind: 'many', count: 2 })
})

test('an approval that was announced and is still open is not announced again', () => {
  assert.equal(announce(new Set([4]), [approval(4)]), null)
})

test('the link goes to the run in the workflow editor', () => {
  assert.equal(approvalHref(approval(2)), '/projects/1/workflows/5/runs/12')
})

test('the headline is the question, or the gate when it asks nothing', () => {
  assert.equal(headline(approval(1, { prompt: 'Publish this?\nIt goes live at once.' })), 'Publish this?')
  assert.equal(headline(approval(1, { prompt: '  ' })), 'Approve listing')
})
