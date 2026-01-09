import { mount } from 'svelte'
import CA460Sync from './CA460Sync.svelte'

const app = mount(CA460Sync, {
  target: document.querySelector('section.content')!,
})

export default app
