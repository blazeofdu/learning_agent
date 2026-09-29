import random
from itertools import combinations


BITS = 30
MAX_VALUE = 1 << BITS


def transform(a):
    n = len(a)

    values = [
        x ^ y
        for x, y in combinations(a, 2)
    ]

    values.sort()
    return values[:n]


def test_one(n, max_steps=60):
    a = [
        random.randrange(MAX_VALUE)
        for _ in range(n)
    ]

    for step in range(max_steps + 1):
        if max(a) - min(a) == 0:
            return True, step, a

        a = transform(a)

    return False, max_steps, a


n = int(input("请输入 n："))
trials = int(input("请输入随机测试次数："))

for test_id in range(1, trials + 1):
    ok, step, result = test_one(n)

    if not ok:
        print("发现 60 次后范围仍不为 0：")
        print(sorted(result))
        break

    print(f"第 {test_id} 组通过，最多在第 {step} 次范围变为 0")
else:
    print(f"全部 {trials} 组随机测试通过")