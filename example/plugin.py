from datasette_llm_accountant import PricingProvider, Accountant, Tx, ModelPricingNotFoundError

from datasette import hookimpl

@hookimpl
def register_llm_accountant_pricing(datasette):
    return HardcodedPricingProvider()

@hookimpl
def register_llm_accountants(datasette):
    return [AccountantTest()]


class HardcodedPricingProvider(PricingProvider):
    def __init__(self):
        self._pricing = {
            "gemini/gemini-2.5-flash": {
                "vendor": "test",
                "input": 3.0,
                "output": 25.0,
            },
            "gemini/gemini-3-flash-preview": {
                "vendor": "test",
                "input": 3.0,
                "output": 25.0,
            },
        }

    def get_model_pricing(self, model_id: str) -> dict:
        if model_id not in self._pricing:
            raise ModelPricingNotFoundError(
                f"Pricing not found for model '{model_id}'. "
                f"Available models: {', '.join(sorted(self._pricing.keys()))}"
            )
        return self._pricing[model_id]

class AccountantTest(Accountant):

    def __init__(self):
        self.reservations = []
        self.settlements = []
        self.rollbacks = []

    async def reserve(self, nanocents: int) -> Tx:
        tx = Tx(f"tx-{len(self.reservations)}")
        self.reservations.append((tx, nanocents))
        return tx

    async def settle(self, tx: Tx, nanocents: int):
        self.settlements.append((tx, nanocents))

    async def rollback(self, tx: Tx):
        self.rollbacks.append(tx)