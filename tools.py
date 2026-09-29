import ast
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
    if len(expression) > 100:
        raise ValueError("表达式太长")

    tree = ast.parse(expression, mode="eval") # 以单个表达式

    def evaluate(node):
        if isinstance(node, ast.Constant): #  语法树节点是不是一个数字常量： int float str
            if isinstance(node.value, (int, float)):
                return node.value

            raise ValueError("只允许数字")

        if isinstance(node, ast.BinOp): # 解析二元运算符
            operator_func = ALLOWED_OPERATORS.get(type(node.op))

            if operator_func is None:
                raise ValueError("不支持的运算符")

            return operator_func(
                evaluate(node.left),
                evaluate(node.right),
            )

        if isinstance(node, ast.UnaryOp):
            operator_func = ALLOWED_OPERATORS.get(type(node.op))

            if operator_func is None:
                raise ValueError("不支持的一元运算")

            return operator_func(
                evaluate(node.operand)
            )

        raise ValueError("表达式格式不支持")

    return evaluate(tree.body)


if __name__ == "__main__":
    print(calculator("2 * (3 + 4)"))