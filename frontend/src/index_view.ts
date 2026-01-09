import { mount } from 'svelte'
import CA460Index from './CA460Index.svelte'

const app = mount(CA460Index, {
  target: document.querySelector('section.content')!,
})

export default app
