
def get_bit(value, n):
    return (value >> n & 1) != 0


def flip_bit(value, n):
    return value ^ (1 << n)


class Buttons:
    """
    Utility class to set buttons in the input report
    TODO: More Buttons
    """
    def __init__(self):
        self.left = 0
        self.middle = 0
        self.right = 0

    def home(self):
        self.middle = flip_bit(self.middle, 4)

    def home_is_set(self):
        return get_bit(self.middle, 4)

    def to_list(self):
        return [self.left, self.middle, self.right]

    def clear(self):
        self.left = self.middle = self.right = 0
