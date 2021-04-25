import logging

from web3 import Web3
from web3.contract import Contract, ContractFunction
from web3.exceptions import TransactionNotFound

import tools
from core import LiquidityPool, Token, TokenAmount, TradePairs
from dex import DexProtocol
from exceptions import InsufficientLiquidity

# Strategy parameters
DEFAULT_MAX_HOPS_FIRST_DEX = 2
MAX_HOPS_SECOND_DEX = 1  # Fixed for this class
DEFAULT_MIN_CONFIRMATIONS = 1
DEFAULT_MAX_TRANSACTION_CHECKS = 20
MAX_GAS_PRICE = 21428571428571  # Equal to 3 BNB/ETH tx cost at 140_000 gas

# Initial gas estimates
DEFAULT_GAS_SHARE_OF_PROFIT = 0.26
HOP_PENALTY = 0.01  # TODO: Simulate more than one hop configuration per arbitrage pair  # noqa: E501
MAX_GAS_MULTIPLIER = 3.5

# Default optimization parameters
INITIAL_VALUE = 1.0  # Initial value in USD to estimate best trade
INCREMENT = 0.001  # Increment to estimate derivatives in optimization
TOLERANCE_USD = 0.01  # Tolerance to stop optimization
MAX_ITERATIONS = 100
USE_FALLBACK = True

log = logging.getLogger(__name__)


class ArbitragePairV1:
    def __init__(
        self,
        token_first: Token,
        token_last: Token,
        first_dex: DexProtocol,
        second_dex: DexProtocol,
        contract: Contract,
        web3: Web3,
        max_hops_first_dex: int = DEFAULT_MAX_HOPS_FIRST_DEX,
        min_confirmations: int = DEFAULT_MIN_CONFIRMATIONS,
        max_transaction_checks: int = DEFAULT_MAX_TRANSACTION_CHECKS,
        gas_share_of_profit: float = DEFAULT_GAS_SHARE_OF_PROFIT,
        max_gas_price: int = MAX_GAS_PRICE,
        raise_at_excessive_gas_price: bool = True,
        optimization_params: dict = None,
    ):
        self.token_first = token_first
        self.token_last = token_last
        self.first_dex = first_dex
        self.second_dex = second_dex
        self.contract = contract
        self.web3 = web3
        self.max_hops_first_dex = max_hops_first_dex
        self.min_confirmations = min_confirmations
        self.max_transaction_checks = max_transaction_checks
        self.gas_share_of_profit = gas_share_of_profit
        self.max_gas_price = max_gas_price
        self.raise_at_excessive_gas_price = raise_at_excessive_gas_price

        optimization_params = optimization_params or {}
        self.opt_initial_value = optimization_params.get('initial_value', INITIAL_VALUE)
        self.opt_increment = optimization_params.get('increment', INCREMENT)
        self.opt_tolerance = optimization_params.get('tolerance', TOLERANCE_USD)
        self.opt_max_iter = optimization_params.get('max_iter', MAX_ITERATIONS)
        self.opt_use_fallback = optimization_params.get('use_fallback', USE_FALLBACK)

        self.amount_last = TokenAmount(token_last)
        self.estimated_result = TokenAmount(token_first)
        self.first_trade: TradePairs = None
        self.second_trade: TradePairs = None

        self.is_disabled = False
        self._is_set = False
        self._is_running = False
        self._transaction_hash = ''
        self.gas_price = 0
        self.gas_cost = 0
        self.estimated_gross_result_usd = 0.0
        self.estimated_net_result_usd = 0.0
        self._n_transaction_checks = 0
        self.block_number: int = None
        self.tx_succeeded: bool = None

    def __repr__(self):
        return (
            f'{self.__class__.__name__}'
            f'({self.token_first.symbol}->{self.token_last.symbol}->{self.token_first.symbol}, '
            f'first_dex={self.first_dex}, '
            f'est_result=US${self.estimated_net_result_usd:,.2f})'
        )

    def _get_gas_cost(self) -> int:
        raise NotImplementedError

    def _get_contract_function(self) -> ContractFunction:
        raise NotImplementedError

    def _get_path_argument(self) -> list[str]:
        raise NotImplementedError

    @property
    def pools(self) -> list[LiquidityPool]:
        return list(set(self.first_dex.pools) | set(self.second_dex.pools))

    @property
    def execution_pools(self) -> list[LiquidityPool]:
        if self.first_trade is None or self.second_trade is None:
            return []
        return self.first_trade.route.pools + self.second_trade.route.pools

    def _estimate_result_int(self, amount_last_int: int) -> int:
        amount_last = TokenAmount(self.token_last, amount_last_int)
        return self._estimate_result(amount_last).amount

    def _estimate_result(self, amount_last: TokenAmount) -> TokenAmount:
        first_trade, second_trade = self._get_arbitrage_trades(amount_last)
        return second_trade.amount_out - first_trade.amount_in

    def _get_arbitrage_trades(self, amount_last: TokenAmount) -> tuple[TradePairs, TradePairs]:
        first_trade = self.first_dex.best_trade_exact_out(
            self.token_first, amount_last, self.max_hops_first_dex, HOP_PENALTY)
        second_trade = self.second_dex.best_trade_exact_in(
            amount_last, self.token_first, MAX_HOPS_SECOND_DEX, HOP_PENALTY)
        return first_trade, second_trade

    def update_estimate(self, block_number: int = None):
        try:
            if self._is_set:
                self._reset()
            self._update_estimate(block_number)
        except InsufficientLiquidity:
            logging.info(f'Insufficient liquidity for {self}, removing it from next iterations')
            self._reset()
            self.is_disabled = True

    def _update_estimate(self, block_number: int):
        usd_price_token_last = tools.price.get_price_usd(self.token_last, self.pools)
        amount_last_initial = TokenAmount(
            self.token_last,
            int(self.opt_initial_value / usd_price_token_last * 10 ** self.token_last.decimals)
        )
        result_initial = self._estimate_result(amount_last_initial)
        if result_initial < 0:
            # If gross result is negative even with small amount, skip optimization
            return
        try:
            int_amount_last, int_result = tools.optimization.optimizer_second_order(
                func=self._estimate_result_int,
                x0=amount_last_initial.amount,
                dx=int(self.opt_increment * 10 ** self.token_last.decimals / usd_price_token_last),
                tol=int(self.opt_tolerance * 10 ** self.token_last.decimals / usd_price_token_last),
                max_iter=self.opt_max_iter,
                use_fallback=self.opt_use_fallback,
            )
        except Exception as e:
            log.info(f'{self}: Error during optimization: {e!r}')
            log.debug('Error: ', exc_info=True)
            return
        if int_amount_last < 0:  # Fail-safe in case optimizer returns negative inputs
            return
        amount_last = TokenAmount(self.token_last, int_amount_last)
        estimated_result = TokenAmount(self.token_first, int_result)
        self._set_arbitrage_params(amount_last, estimated_result, block_number)

    def _set_arbitrage_params(
        self,
        amount_last: TokenAmount,
        estimated_result: TokenAmount,
        block_number: int
    ):
        self._is_set = True
        self.amount_last = amount_last
        self.estimated_result = estimated_result
        self.block_number = block_number
        self.first_trade, self.second_trade = self._get_arbitrage_trades(amount_last)

        token_usd_price = tools.price.get_price_usd(estimated_result.token, self.pools, self.web3)
        self.estimated_gross_result_usd = estimated_result.amount_in_units * token_usd_price
        self.gas_cost = self._get_gas_cost()

        gas_cost_usd = tools.price.get_gas_cost_usd(self.gas_cost)
        gas_premium = self.gas_share_of_profit * self.estimated_gross_result_usd / gas_cost_usd
        gas_premium = max(gas_premium, 1)

        baseline_gas_price = tools.price.get_gas_price()
        self.gas_price = int(baseline_gas_price * gas_premium)
        if self.gas_price > self.max_gas_price:
            if self.raise_at_excessive_gas_price:
                raise Exception(
                    f'{self}: Excessive gas price (estimated_gross_result_usd='
                    f'{self.estimated_gross_result_usd:.2f})'
                )
            self.gas_price = self.max_gas_price
            gas_premium = self.gas_price / baseline_gas_price
        self.estimated_net_result_usd = self.estimated_gross_result_usd - gas_cost_usd * gas_premium

    def _get_tx_params(self):
        return {
            'func': self._get_contract_function(),
            'path': self._get_path_argument(),
            'amountLast': self.amount_last.amount,
            'max_gas_': int(self.gas_cost * MAX_GAS_MULTIPLIER),
            'gas_price_': self.gas_price,
        }

    def dry_run(self):
        tools.transaction.dry_run_contract_tx(**self._get_tx_params())

    def execute(self):
        transaction_hash = tools.transaction.sign_and_send_contract_tx(**self._get_tx_params())
        self._is_running = True
        self._transaction_hash = transaction_hash
        log.info(f'Sent transaction with hash {transaction_hash}')
        log.info(
            f'Trades: {self.first_dex}:{self.first_trade}; {self.second_dex}:{self.second_trade}')
        est_tx_cost = self.gas_price * self.gas_cost / 10 ** tools.price.get_native_token_decimals()
        log.info({
            'tx_hash': transaction_hash,
            'block_number': self.block_number,
            'estimated_net_result_usd': self.estimated_net_result_usd,
            'estimated_gross_result_usd': self.estimated_gross_result_usd,
            'gas_share_of_profit': self.gas_share_of_profit,
            'gas_price': self.gas_price,
            'est_tx_cost': est_tx_cost,
            'token_first_symbol': self.token_first.symbol,
            'token_last_symbol': self.token_last.symbol,
            'token_last_amount': self.amount_last.amount,
            'n_hops': len(self.first_trade.route.pools),
        })
        reserves = {pool: pool.reserves for pool in self.execution_pools}
        log.debug(f'Reserves: {reserves}')

    def _reset(self):
        self._is_set = False
        self._is_running = False
        self._transaction_hash = ''
        self.amount_last = TokenAmount(self.token_last)
        self.estimated_result = TokenAmount(self.token_first)
        self.first_trade = None
        self.second_trade = None
        self.gas_price = 0
        self.gas_cost = 0
        self.estimated_gross_result_usd = 0.0
        self.estimated_net_result_usd = 0.0
        self._n_transaction_checks = 0
        self.block_number = None
        self.tx_succeeded = None

    def is_running(self, current_block: int) -> bool:
        if not self._is_running:
            return False
        try:
            receipt = self.web3.eth.getTransactionReceipt(self._transaction_hash)
        except TransactionNotFound:
            log.info(f'Transaction {self._transaction_hash} not found in node')
            self._n_transaction_checks += 1
            if self._n_transaction_checks >= self.max_transaction_checks:
                log.warning(
                    f'Transaction {self._transaction_hash} not found after '
                    f'{self.max_transaction_checks} checks.'
                )
                return False
            return True
        if receipt.status == 0:
            log.info(f'Transaction {self._transaction_hash} failed (gas_used={receipt.gasUsed})')
            self.tx_succeeded = False
            return False
        elif current_block - receipt.blockNumber < (self.min_confirmations - 1):
            return True
        # Minimum amount of confimations passed
        log.info(
            f'Transaction {self._transaction_hash} succeeded (gas_used={receipt.gasUsed}). '
            f'(Estimated profit: {self.estimated_net_result_usd})'
        )
        self.tx_succeeded = True
        return False
