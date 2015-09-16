from __future__ import print_function


__author__ = 'marco'


class Buckets(object):
    def __init__(self, data, buckets):
        self.lower_bound = min(data)
        self.upper_bound = max(data)
        self.data = []
        for val in data:
            self.data.append(val)
        self.step = float(self.upper_bound - self.lower_bound) / buckets
        self.buckets = [0 for _ in range(buckets)]
        self.computed = False

    def get_buckets(self):
        if self.computed:
            return self.buckets

        for value in self.data:
            if value < self.lower_bound or value > self.upper_bound + self.step:
                continue
            bucket = int((float(value) - self.lower_bound) / self.step)
            if 0 <= bucket < len(self.buckets):
                self.buckets[bucket] += 1
        self.computed = True
        return self.buckets
