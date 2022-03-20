import logging
import sys


root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)


class Multiplier:

    def multiply(self, a:int, b:int) -> int:
        return a * b


if __name__ == '__main__':
    def multiply_with_logging(func):
        def impl(*args, **kwargs):
            logging.debug(f"Call to {func.__qualname__} with arguments {args[1:]}")
            ret_value = func(*args, **kwargs)
            logging.debug(f"Call to {func.__qualname__} returned {ret_value}")
            return ret_value
        return impl

    multiplier = Multiplier()
    result = multiplier.multiply(3, 4)
    logging.debug(f"Result is {result}")

    Multiplier.multiply = multiply_with_logging(Multiplier.multiply)
    result = multiplier.multiply(3, 4)
    logging.debug(f"Result is {result}")
