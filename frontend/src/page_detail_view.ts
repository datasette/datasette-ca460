import { mount } from 'svelte'
import CA460PageDetail from './CA460PageDetail.svelte'

const app = mount(CA460PageDetail, {
  target: document.querySelector('section.content')!,
})

export default app
