import assert from 'node:assert/strict'
import { test } from 'node:test'
import { effectiveEffort, effortAfterModelChange, effortsOf, modelLabel, type ModelInfo } from './models.ts'

const models: ModelInfo[] = [
  { id: 'big', label: 'Big', efforts: ['low', 'medium', 'high', 'ultra'], default_effort: 'low' },
  { id: 'small', label: 'Small', efforts: ['low', 'medium', 'high'], default_effort: 'medium' },
]

test('a model offers its own efforts, and an unknown model offers all of them', () => {
  assert.deepEqual(effortsOf(models, 'small'), ['low', 'medium', 'high'])
  assert.ok(effortsOf(models, 'brand-new').includes('ultra'))
})

test('an unsupported effort becomes the default of the model, an unknown model keeps what it was given', () => {
  assert.equal(effectiveEffort(models, 'small', 'ultra'), 'medium')
  assert.equal(effectiveEffort(models, 'big', 'ultra'), 'ultra')
  assert.equal(effectiveEffort(models, 'brand-new', 'ultra'), 'ultra')
})

test('changing the model keeps the effort only while the new model accepts it', () => {
  assert.equal(effortAfterModelChange(models, 'small', 'ultra'), '')
  assert.equal(effortAfterModelChange(models, 'small', 'high'), 'high')
  assert.equal(effortAfterModelChange(models, 'small', ''), '')
})

test('a model outside the list is named as it was written', () => {
  assert.equal(modelLabel(models, 'big'), 'Big')
  assert.equal(modelLabel(models, 'brand-new'), 'brand-new')
})
