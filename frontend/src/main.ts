import { mount } from 'svelte'
import './app.css'
import { initializeAppearance } from './lib/appearance'
import App from './App.svelte'

initializeAppearance()

const app = mount(App, {
  target: document.getElementById('app')!,
})

export default app
