import pytest
import ast
import tools

from tools import calculator,get_current_time


@pytest.mark.parametrize( #@pytest.mark.parametrize 表示用多组参数重复运行同一个测试函数。
    ("expression,expected"),#合法
    [
        ("1+1", 2),
        ("1+2", 3),
        ("10 / 2", 5),
        ("2 ** 3", 8),
        ("-5 + 2", -3),
    ],
)

def test_calculator_valid_expression(expression, expected): # pytest会自动调用test开头的函数
    assert calculator(expression) == expected #assert 断言等于if 判断条件是否满足to

@pytest.mark.parametrize(
    ("expression"),
    [
        "hello world",
        "2//3",
        "abs(-1)",
        "1; 2",
    ],
)

def test_calculator_rejects_unsupported_expressions(expression): #用来测试代码是否会抛出异常
    with pytest.raises((ValueError,SyntaxError)): #(,) 元组 只能是这些异常
        calculator(expression)


def test_calculator_rejects_long_expression():
    with pytest.raises(ValueError,match="表达式太长"): # 异常字符子串是否有表达式
        calculator("1"*101)


def test_current_time_format(): #测试时间函数
    result = get_current_time()

    assert len(result) == 19
    assert result[4] == "-"
    assert result[7] == "-"
    assert result[10] == " "
    assert result[13] == ":"
    assert result[16] == ":"


@pytest.mark.parametrize("expression", [
    "True", "False + 1", "'text'", "1j", "(-1) ** 0.5", "1e309",
    "1000000000001", "10 ** 100", "[]", "1 % 2", "1 << 2",
    "__import__('os')", "" , "-" * 14 + "1", "+".join(["1"] * 24),
])
def test_calculator_rejects_unsafe_or_excessive_values(expression):
    with pytest.raises((ValueError, SyntaxError)):
        calculator(expression)


def test_large_exponent_is_rejected_before_power_runs(monkeypatch):
    def must_not_run(*args):
        pytest.fail("应在执行幂运算之前拒绝巨大指数")

    monkeypatch.setitem(tools.ALLOWED_OPERATORS, ast.Pow, must_not_run)
    with pytest.raises(ValueError, match="指数"):
        calculator("9 ** 999999999")


@pytest.mark.parametrize("expression, expected", [
    ("1000000000000", 10 ** 12), ("2 * (3 + 4)", 14),
    ("2 ** -2", 0.25), ("  2 + 3  ", 5),
])
def test_calculator_boundaries_and_parentheses(expression, expected):
    assert calculator(expression) == expected


def test_calculator_division_by_zero():
    with pytest.raises(ZeroDivisionError):
        calculator("1 / 0")



