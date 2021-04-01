from typing import Callable

DEFAULT_MAX_ITER = 100


def first_derivative(func: Callable[int, int], x_i: int, dx: int) -> float:
    return (func(x_i + dx) - func(x_i)) / dx


def second_derivative(func: Callable[int, int], x_i: int, dx: int) -> float:
    return (func(x_i + dx) - 2 * func(x_i) + func(x_i - dx)) / dx ** 2


def optimizer_second_order(
    func: Callable[int, int],
    x0: int,
    dx: int,
    tolerance: int = 10 ** 18,
    max_iter: int = DEFAULT_MAX_ITER,
    positive_only: bool = True
) -> tuple[int, int]:
    """Maximizes function using Newton's method and finite differences, where variables are in int

    Args:
        func (Callable): Function to be maximized
        x0 (int): Initial guess
        dx (int): Interval to calculate derivatives
        max_iter (int): Maximum number of iterations
        tolerance (tolerance): Absolute tolerance between iterations to stop optimization

    Returns:
        tuple[int, int]: Result in x and func(x)
    """
    x_i = x0
    for i in range(max_iter):
        x_i_next = int(x_i - first_derivative(func, x_i, dx) / second_derivative(func, x_i, dx))
        if abs(x_i_next - x_i) < tolerance:
            break
        x_i = x_i_next
    return x_i_next, func(x_i_next)
