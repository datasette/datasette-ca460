import { mount } from 'svelte'
import CA460Document from './CA460Document.svelte'

const app = mount(CA460Document, {
  target: document.querySelector('section.content')!,
})

export default app
