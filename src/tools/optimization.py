from typing import Callable, Union

from exceptions import InsufficientLiquidity

DEFAULT_MAX_ITER = 100

Number = Union[int, float]


def optimizer_second_order(
    func: Callable[int, int],
    x0: int,
    dx: int,
    tol: int = 10 ** 18,
    max_iter: int = DEFAULT_MAX_ITER,
    catch_errors: tuple[Exception] = (InsufficientLiquidity,),
    learning_rate: float = 0.5,
) -> tuple[int, int]:
    """Maximizes function using Newton's method and finite differences, where variables are in int.

    Args:
        func (Callable): Function to be maximized
        x0 (int): Initial guess
        dx (int): Interval to calculate derivatives
        tol (int): Absolute tolerance between iterations to stop optimization
        learning_rate (float): Multiplier to Newton method step
        max_iter (int): Maximum number of iterations
        catch_errors (tuple): Exceptions to be catched from func that will re-compute x

    Returns:
        tuple[int, int]: Result in x and func(x)
    """
    x_i = x0
    for i in range(max_iter):
        try:
            f_x_i = func(x_i)
            f_x_ip = func(x_i + dx)
            f_x_im = func(x_i - dx)
        except catch_errors:
            x_i //= 2
            continue
        first_derivative = (f_x_ip - f_x_im) / (2 * dx)
        second_derivative = (f_x_ip - 2 * f_x_i + f_x_im) / (dx ** 2)
        if second_derivative == 0:
            dx //= 2
            continue
        x_i_next = int(x_i - first_derivative / second_derivative * learning_rate)
        if abs(x_i_next - x_i) < tol:
            break
        x_i = x_i_next
    return x_i_next, func(x_i_next)
