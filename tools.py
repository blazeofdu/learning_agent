import ast
import math
import operator as op

from datetime import datetime

ALLOWED_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.USub: op.neg,
}

def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def calculator(expression: str):
    if not isinstance(expression, str):
        raise ValueError("表达式必须是字符串")
    if len(expression) > 100:
        raise ValueError("表达式太长")

    tree = ast.parse(expression.strip(), mode="eval") # 以单个表达式解析，不执行 eval()
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueError("表达式太复杂")

    def check_number(value):
        # bool 是 int 的子类，因此这里使用 type，而不是 isinstance。
        if type(value) not in (int, float):
            raise ValueError("只允许实数，不支持布尔值或复数")
        if abs(value) > 10 ** 12 or not math.isfinite(value):
            raise ValueError("数值绝对值不能超过 10^12，且必须是有限数")
        return value

    def evaluate(node, depth=0):
        if depth > 12:
            raise ValueError("表达式嵌套过深")
        if isinstance(node, ast.Constant): #  语法树节点是不是一个数字常量： int float str
            return check_number(node.value)

        if isinstance(node, ast.BinOp): # 解析二元运算符
            operator_func = ALLOWED_OPERATORS.get(type(node.op))

            if operator_func is None:
                raise ValueError("不支持的运算符")

            left = evaluate(node.left, depth + 1)
            right = evaluate(node.right, depth + 1)
            # 在做幂运算之前限制指数，短表达式也不能触发巨大计算。
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("指数绝对值不能超过 100")
            return check_number(operator_func(left, right))

        if isinstance(node, ast.UnaryOp):
            operator_func = ALLOWED_OPERATORS.get(type(node.op))

            if operator_func is None:
                raise ValueError("不支持的一元运算")

            return check_number(operator_func(evaluate(node.operand, depth + 1)))

        raise ValueError("表达式格式不支持")

    return evaluate(tree.body)


if __name__ == "__main__":
    print(calculator("2 * (3 + 4)"))
