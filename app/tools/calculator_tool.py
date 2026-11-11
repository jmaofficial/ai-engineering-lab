def calculate(operation: str, a: float, b: float) -> float:
    """
    Perform a mathematical operation on two numbers.

    Args:
        operation: One of 'add', 'subtract', 'multiply', 'divide'.
        a: First number.
        b: Second number.

    Returns:
        The result of the calculation.
    """

    valid_ops = {
        'add': lambda x, y: x + y,
        'subtract': lambda x, y: x - y,
        'multiply': lambda x, y: x * y,
        'divide': lambda x, y: x / y 
    }
    if operation not in valid_ops:
        raise ValueError(f"Invalid operation '{operation}'. Valid operations are: {', '.join(valid_ops.keys())}.")
    else:
        print(f"🔧 TOOL EXECUTED: calculate('{operation}', {a}, {b})")
        return float(valid_ops[operation](a, b))