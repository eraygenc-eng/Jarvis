from typing import Literal

from langchain.tools import tool


@tool
def calculator(
    a: float,
    b: float,
    operation: Literal["add", "subtract", "multiply", "divide"],
) -> float:
    """Perform a basic mathematical operation.

    operation must be one of:
    - add
    - subtract
    - multiply
    - divide
    """

    if operation == "add":
        return a + b

    elif operation == "subtract":
        return a - b

    elif operation == "multiply":
        return a * b

    elif operation == "divide":
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b

    else:
        raise ValueError("Unknown Operation")