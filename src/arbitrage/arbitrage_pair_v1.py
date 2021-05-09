import json
import logging
from datetime import datetime
from enum import Enum
from typing import Callable

from web3 import Web3
from web3.contract import Contract, ContractFunction
from web3.exceptions import TransactionNotFound

import configs
import tools
from core import LiquidityPool, Route, RoutePairs, Token, TokenAmount, TradePairs, TradePools
from dex import DexProtocol
from exceptions import InsufficientLiquidity, NotProfitable, OptimizationError

from .encode_data import decompose_amount

log = logging.getLogger(__name__)

# Strategy parameters
DEFAULT_MIN_CONFIRMATIONS = 2
DEFAULT_MAX_TRANSACTION_CHECKS = 20
MAX_GAS_PRICE = 21428571428571  # Equal to 3 BNB/ETH tx cost at 140_000 gas
BASE_GAS_COST = 140_000

# Default optimization parameters
INITIAL_VALUE = 1.0  # Initial value in USD to estimate best trade
INCREMENT = 0.001  # Increment to estimate derivatives in optimization
TOLERANCE_USD = 0.01  # Tolerance to stop optimization
MAX_ITERATIONS = 100
USE_FALLBACK = True

# Gas parameters
DEFAULT_GAS_SHARE_OF_PROFIT = 0.26
MAX_GAS_MULTIPLIER = 3.5
MIN_ARBITRAGE_LOGS = 4  # At least one CHI transfer and three ERC20 transfers

PREFERED_TOKENS_FILE = 'addresses/preferred_tokens.json'
TOKEN_MULTIPLIER_WEIGHT = 0.01
TOKEN_MULTIPLIERS = {
    Token(configs.CHAIN_ID, **data['token']): 1 + data['weight'] * TOKEN_MULTIPLIER_WEIGHT
    for data in json.load(open(PREFERED_TOKENS_FILE))[str(configs.CHAIN_ID)]
}


class HighGasPriceStrategy(Enum):
    baseline_3x = 'baseline_3x'
    recalculate_at_max = 'recalculate_at_max'
    raise_ = 'raise_'


class TxStatus(str, Enum):
    empty = ''
    succeeded = 'succeeded'
    failed = 'failed'
    not_found = 'not_found'


class ArbitragePairV1:
    def __init__(
        self,
        token_first: Token,
        token_last: Token,
        route_0: Route,
        route_1: RoutePairs,
        dex_0: DexProtocol,
        dex_1: DexProtocol,
        contract: Contract,
        web3: Web3,
        min_confirmations: int = DEFAULT_MIN_CONFIRMATIONS,
        max_transaction_checks: int = DEFAULT_MAX_TRANSACTION_CHECKS,
        base_bas_cost: int = BASE_GAS_COST,
        gas_share_of_profit: float = DEFAULT_GAS_SHARE_OF_PROFIT,
        max_gas_price: int = MAX_GAS_PRICE,
        max_gas_multiplier: float = MAX_GAS_MULTIPLIER,
        high_gas_price_strategy: HighGasPriceStrategy = HighGasPriceStrategy.baseline_3x,
        decomposer_function: Callable = decompose_amount,
        optimization_params: dict = None,
        w_swap_available: bool = False,
    ):
        """"The V1 pair has two fixed routes:
            - route_0 has a single generic liquidity pool
            - route_1 is a route of one or more liquidity pairs
            Flash trade occurs at the last pair of the route_1
        """
        assert len(route_0.pools) == 1
        assert len(route_1.pools) >= 1
        self.token_first = token_first
        self.token_last = token_last
        self.route_0 = route_0
        self.dex_0 = dex_0
        self.route_1 = route_1
        self.dex_1 = dex_1
        self.contract = contract
        self.web3 = web3
        self.min_confirmations = min_confirmations
        self.max_transaction_checks = max_transaction_checks
        self.base_gas_cost = base_bas_cost
        self.gas_share_of_profit = gas_share_of_profit
        self.max_gas_price = max_gas_price
        self.max_gas_multiplier = max_gas_multiplier
        self.high_gas_price_strategy = high_gas_price_strategy
        self.decomposer_function = decomposer_function

        optimization_params = optimization_params or {}
        self.opt_initial_value = optimization_params.get('initial_value', INITIAL_VALUE)
        self.opt_dx = optimization_params.get('increment', INCREMENT)
        self.opt_tol = optimization_params.get('tolerance', TOLERANCE_USD)
        self.opt_max_iter = optimization_params.get('max_iter', MAX_ITERATIONS)
        self.opt_use_fallback = optimization_params.get('use_fallback', USE_FALLBACK)

        self.wrapped_currency = tools.price.get_wrapped_currency_token()
        self.wrapped_currency.contract = web3.eth.contract(
            address=self.wrapped_currency.address,
            abi=self.wrapped_currency.abi,
        )
        self._w_swap = (
            w_swap_available
            and route_0.token_in == route_1.token_out == self.wrapped_currency
            and self.dex_0 != self.dex_1
            )

        self.result_multiplier: float = TOKEN_MULTIPLIERS.get(self.token_first, 1.0)
        self.flag_disabled = False
        self.reference_price_pools = [
            pool
            for pool in self.dex_0.pools + self.dex_1.pools
            if token_first in pool.tokens or token_last in pool.tokens
        ]

        # Arbitrage params set before execution
        self.flag_set = False
        self.timestamp_found: float = 0.0
        self.block_found: int = None
        self.amount_last = TokenAmount(token_last)
        self._amount_last_exp: int = None
        self._amount_last_mant: int = None
        self.estimated_result = TokenAmount(token_first)
        self.trade_0: TradePools = None
        self.trade_1: TradePairs = None
        self.execute_w_swap = False
        self.result_token_usd_price: float = 0.0
        self.estimated_gross_result_usd = 0.0
        self.gas_price = 0
        self.gas_cost = 0
        self.estimated_tx_cost = 0.0
        self.estimated_net_result_usd = 0.0

        # Arbitrage params set during / after execution
        self.flag_execute = False
        self._is_running = False
        self.timestamp_sent: float = 0.0
        self.block_executed: int = None
        self.tx_hash = ''
        self.n_tx_checks = 0
        self.tx_status = TxStatus.empty
        self.gas_used: int = None
        self.block_send_delay: int = None

    def __repr__(self):
        return (
            f'{self.__class__.__name__}('
            f'{self.dex_0}({self.route_0.symbols}), '
            f'{self.dex_1}({self.route_1.symbols}), '
            f'est_result=US${self.estimated_net_result_usd:,.2f})'
        )

    def _get_gas_cost(self) -> int:
        raise NotImplementedError

    def _get_contract_function(self) -> ContractFunction:
        raise NotImplementedError

    def _get_function_arguments(self) -> dict:
        raise NotImplementedError

    def _get_contract_test_function(self):
        return self._get_contract_function()

    @property
    def pools(self) -> list[LiquidityPool]:
        return self.route_0.pools + self.route_1.pools

    @property
    def tokens(self) -> list[Token]:
        return list(set(self.route_0.tokens + self.route_1.tokens))

    @property
    def adjusted_profit(self) -> float:
        return self.estimated_net_result_usd * self.result_multiplier

    def _get_contract_wrapped_currency_balance(self) -> TokenAmount:
        balance = self.wrapped_currency.contract.functions.balanceOf(self.contract.address).call()
        return TokenAmount(self.wrapped_currency, balance)

    def _estimate_result_int(self, amount_last_int: int) -> int:
        amount_last = TokenAmount(self.token_last, amount_last_int)
        return self.estimate_result(amount_last).amount

    def estimate_result(self, amount_last: TokenAmount, w_swap: bool = False) -> TokenAmount:
        trade_0, trade_1 = self.get_arbitrage_trades(amount_last, w_swap)
        if w_swap:
            return trade_1.amount_out - trade_0.amount_in
        return trade_0.amount_out - trade_1.amount_in

    def get_arbitrage_trades(
        self,
        amount_last: TokenAmount,
        w_swap: bool = False,
    ) -> tuple[TradePools, TradePairs]:
        if w_swap:
            trade_1 = TradePairs(self.route_1, amount_out=amount_last)
            trade_0 = TradePairs(self.route_0, amount_out=trade_1.amount_in)
        else:
            trade_0 = TradePools(self.route_0, amount_in=amount_last)
            trade_1 = TradePairs(self.route_1, amount_out=amount_last)
        return trade_0, trade_1

    def update_estimate(self, block_number: int = None):
        if self.flag_disabled:
            return
        try:
            if self.flag_set:
                self.reset()
            amount_last, estimated_result = self.get_updated_results()
            self._set_arbitrage_params(amount_last, estimated_result, block_number)
        except InsufficientLiquidity:
            log.info(f'Insufficient liquidity for {self}, removing it from next iterations')
            reserves = {pool: pool.reserves for pool in self.pools}
            log.debug(f'Reserves: {reserves}')
            self.reset()
            self.flag_disabled = True
        except OptimizationError as e:
            log.debug(f'{self}: Error during optimization: {e!r}')
            return
        except NotProfitable:
            return

    def get_updated_results(self) -> tuple[TokenAmount, TokenAmount]:
        usd_price_token_last = tools.price.get_price_usd(
            self.token_last, self.reference_price_pools, self.web3)
        amount_last_initial = TokenAmount(
            self.token_last,
            round(self.opt_initial_value / usd_price_token_last * 10 ** self.token_last.decimals)
        )
        result_initial = self.estimate_result(amount_last_initial)
        if result_initial < 0:
            # If gross result is negative even with small amount, skip optimization
            raise NotProfitable
        try:
            int_amount_last, int_result = tools.optimization.optimizer_second_order(
                func=self._estimate_result_int,
                x0=amount_last_initial.amount,
                dx=round(self.opt_dx * 10 ** self.token_last.decimals / usd_price_token_last),
                tol=round(self.opt_tol * 10 ** self.token_last.decimals / usd_price_token_last),
                max_iter=self.opt_max_iter,
                use_fallback=self.opt_use_fallback,
            )
        except Exception as e:
            raise OptimizationError(e.args)
        if int_amount_last < 0:  # Fail-safe in case optimizer returns negative inputs
            raise OptimizationError('Negative int_amount_last')
        amount_last = TokenAmount(self.token_last, int_amount_last)
        estimated_result = TokenAmount(self.token_first, int_result)
        return amount_last, estimated_result

    def _set_arbitrage_params(
        self,
        amount_last: TokenAmount,
        estimated_result: TokenAmount,
        block_number: int,
    ):
        self.flag_set = True
        self.timestamp_found = datetime.now().timestamp()
        self.block_found = block_number
        if self._w_swap and amount_last < self._get_contract_wrapped_currency_balance():
            self.execute_w_swap = True
            amount, exp, mant = self.decomposer_function(amount_last)
            self._amount_last_exp = exp
            self._amount_last_mant = mant
            amount_last.amount = amount
            estimated_result = self.estimate_result(amount_last, w_swap=True)
        self.amount_last = amount_last
        self.estimated_result = estimated_result
        self.trade_0, self.trade_1 = self.get_arbitrage_trades(
            amount_last, w_swap=self.execute_w_swap)

        self.result_token_usd_price = tools.price.get_price_usd(
            estimated_result.token, self.reference_price_pools, self.web3)
        self.estimated_gross_result_usd = \
            estimated_result.amount_in_units * self.result_token_usd_price
        self.gas_cost = self._get_gas_cost()

        base_gas_cost_usd = tools.price.get_gas_cost_usd(self.base_gas_cost)
        gas_premium = self.gas_share_of_profit * self.estimated_gross_result_usd / base_gas_cost_usd
        gas_premium = max(gas_premium, 1.0)

        baseline_gas_price = tools.price.get_gas_price()
        gas_price = round(baseline_gas_price * gas_premium)
        if gas_price > self.max_gas_price:
            gas_price, gas_premium = self._process_high_gas_price(baseline_gas_price, gas_price)
        self.gas_price = gas_price
        self.estimated_tx_cost = \
            self.gas_price * self.gas_cost / 10 ** tools.price.get_native_token_decimals()
        gas_cost_usd = tools.price.get_gas_cost_usd(self.gas_cost)
        self.estimated_net_result_usd = self.estimated_gross_result_usd - gas_cost_usd * gas_premium

    def _process_high_gas_price(self, baseline_gas_price: int, gas_price: int) -> tuple[int, float]:
        if self.high_gas_price_strategy == HighGasPriceStrategy.baseline_3x:
            log.info('High gas price detected, using fallback strategy baseline_3x')
            return 3 * baseline_gas_price, 3.0
        if self.high_gas_price_strategy == HighGasPriceStrategy.recalculate_at_max:
            log.info('High gas price detected, using fallback strategy recalculate_at_max')
            return self.max_gas_price, self.max_gas_price / baseline_gas_price
        raise Exception(
            f'{self}: Excessive gas price (estimated_gross_result_usd='
            f'{self.estimated_gross_result_usd:.2f})'
        )

    def _get_tx_arguments(self, test: bool = False):
        return {
            'func': self._get_contract_test_function() if test else self._get_contract_function(),
            **self._get_function_arguments(),
            'max_gas_': int(self.gas_cost * self.max_gas_multiplier),
            'gas_price_': self.gas_price,
        }

    def dry_run(self):
        tools.transaction.dry_run_contract_tx(**self._get_tx_arguments(test=True))

    def get_params(self) -> dict:
        return {
            'tx_hash': self.tx_hash,
            'to': self.contract.address,
            'block_found': self.block_found,
            'timestamp_found': self.timestamp_found,
            'amount_last': self.amount_last.amount,
            'estimated_result_tokens': self.estimated_result.amount,
            'estimated_gross_result_usd': self.estimated_gross_result_usd,
            'gas_price': self.gas_price,
            'estimated_tx_cost': self.estimated_tx_cost,
            'estimated_net_result_usd': self.estimated_net_result_usd,
            'gas_share_of_profit': self.gas_share_of_profit,
            'base_gas_cost': self.base_gas_cost,
            'fn_name': self._get_contract_function().fn_name,
            'execute_w_swap': self.execute_w_swap,
        }

    def get_execution_stats(self) -> dict:
        return {
            'tx_hash': self.tx_hash,
            'timestamp_sent': self.timestamp_sent,
            'block_executed': self.block_executed,
            'tx_status': self.tx_status,
            'gas_used': self.gas_used,
            'block_send_delay': self.block_send_delay,
        }

    def get_tx_stats(self) -> dict:
        return self.get_params() | self.get_execution_stats()

    def execute(self):
        self.flag_execute = True
        self._is_running = True
        self.tx_hash = tools.transaction.sign_and_send_contract_tx(**self._get_tx_arguments())
        self.timestamp_sent = datetime.now().timestamp()
        log.info(f'Sent transaction with hash {self.tx_hash}')
        log.info(f'Trades: {self.dex_0}:{self.trade_0}; {self.dex_1}:{self.trade_1}')
        log.info(self.get_params())
        reserves = {pool: pool.reserves for pool in self.pools}
        log.debug(f'Reserves: {reserves}')

    def reset(self):
        self.flag_set = False
        self.timestamp_found = 0.0
        self.block_found = None
        self.amount_last = TokenAmount(self.token_last)
        self._amount_last_exp = None
        self._amount_last_mant = None
        self.estimated_result = TokenAmount(self.token_first)
        self.trade_0 = None
        self.trade_1 = None
        self.execute_w_swap = False
        self.result_token_usd_price = 0.0
        self.estimated_gross_result_usd = 0.0
        self.gas_price = 0
        self.gas_cost = 0
        self.estimated_tx_cost = 0.0
        self.estimated_net_result_usd = 0.0

        self.flag_execute = False
        self._is_running = False
        self.timestamp_sent = 0.0
        self.block_executed = None
        self.tx_hash = ''
        self.n_tx_checks = 0
        self.tx_status = TxStatus.empty
        self.gas_used = None
        self.block_send_delay = None

    def is_running(self, current_block: int = None) -> bool:
        if not self._is_running:
            return False
        try:
            receipt = self.web3.eth.getTransactionReceipt(self.tx_hash)
        except TransactionNotFound:
            log.info(f'Transaction {self.tx_hash} not found in node')
            self.n_tx_checks += 1
            if self.n_tx_checks >= self.max_transaction_checks:
                log.warning(
                    f'Transaction {self.tx_hash} not found after '
                    f'{self.max_transaction_checks} checks.'
                )
                self.tx_status = TxStatus.not_found
                return False
            return True
        self.gas_used = receipt.gasUsed
        self.block_executed = receipt.blockNumber
        self.block_send_delay = self.block_executed - self.block_found - 1
        if receipt.status == 0 or len(receipt.logs) < MIN_ARBITRAGE_LOGS:
            log.info(f'Transaction {self.tx_hash} failed (gas_used={self.gas_used})')
            self.tx_status = TxStatus.failed
            log.info(self.get_execution_stats())
            return False
        elif (
            current_block is not None
            and current_block - self.block_executed < (self.min_confirmations - 1)
        ):
            return True
        # Minimum amount of confimations passed
        log.info(
            f'Transaction {self.tx_hash} succeeded (gas_used={self.gas_used}). '
            f'(Estimated profit: {self.estimated_net_result_usd})'
        )
        self.tx_status = TxStatus.succeeded
        log.info(self.get_execution_stats())
        return False
