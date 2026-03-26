from datasette import hookimpl
from contextlib import asynccontextmanager


@hookimpl
def llm_prompt_context(datasette, model_id, prompt, purpose, actor):
    @asynccontextmanager
    async def wrapper(result):
        print(f"[example] prompt starting: model={model_id} purpose={purpose}")
        yield
        async def on_complete(response):
            usage = await response.usage()
            print(f"[example] prompt done: model={model_id} purpose={purpose} usage={usage}")
        await result.response.on_done(on_complete)

    return wrapper
