import unittest
from math_utils import fibonacci

class TestMathUtils(unittest.TestCase):
    def test_fibonacci(self):
        # Base cases
        self.assertEqual(fibonacci(0), 0)
        self.assertEqual(fibonacci(1), 1)
        
        # Subsequent numbers
        self.assertEqual(fibonacci(2), 1)
        self.assertEqual(fibonacci(3), 2)
        self.assertEqual(fibonacci(4), 3)
        self.assertEqual(fibonacci(5), 5)
        self.assertEqual(fibonacci(6), 8)
        self.assertEqual(fibonacci(10), 55)
        
        # Negative input should raise ValueError
        with self.assertRaises(ValueError):
            fibonacci(-1)

if __name__ == '__main__':
    unittest.main()
