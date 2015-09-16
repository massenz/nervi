from utils.buckets import Buckets

__author__ = 'marco'


import unittest


class BucketTest(unittest.TestCase):

    def test_bucket(self):
        data = [1, 1, 2, 3, 4, 2, 2.5, 3.4, 3]
        num = 4
        b = Buckets(data, num)
        res = b.get_buckets()
        print(res)
        self.assertEqual(num, len(res))
        self.assertEqual(2, res[0])
        self.assertEqual(len(data), sum(res))
