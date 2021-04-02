from typing import Callable

DEFAULT_MAX_ITER = 100


def optimizer_second_order(
    func: Callable[int, int],
    x0: int,
    dx: int,
    tol: int = 10 ** 18,
    max_iter: int = DEFAULT_MAX_ITER,
    positive_only: bool = True
) -> tuple[int, int]:
    """Maximizes function using Newton's method and finite differences, where variables are in int.
        Recommended for convex functions

    Args:
        func (Callable): Function to be maximized
        x0 (int): Initial guess
        dx (int): Interval to calculate derivatives
        tol (int): Absolute tolerance between iterations to stop optimization
        max_iter (int): Maximum number of iterations

    Returns:
        tuple[int, int]: Result in x and func(x)
    """
    x_i = x0
    for i in range(max_iter):
        f_x_i = func(x_i)
        f_x_ip = func(x_i + dx)
        f_x_im = func(x_i - dx)
        first_derivative = (f_x_ip - f_x_im) / (2 * dx)
        second_derivative = (f_x_ip - 2 * f_x_i + f_x_im) / (dx ** 2)
        x_i_next = int(x_i - first_derivative / second_derivative)
        if abs(x_i_next - x_i) < tol:
            break
        x_i = x_i_next
    return x_i_next, func(x_i_next)
