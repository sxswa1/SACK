import ast  # 抽象语法树
import os
import astor
from _ast import (withitem, alias, keyword, arg, arguments, ExceptHandler, comprehension, NotIn, NotEq, LtE, Lt, IsNot,
                  Is, In, GtE, Gt, Eq, USub, UAdd, Not, Invert, Sub, RShift, Pow, MatMult, Mult, Mod, LShift, FloorDiv,
                  Div, BitXor, BitOr, BitAnd, Add, Or, And, Store, Load, Del, Tuple, List, Name, Starred, Subscript,
                  Attribute, NamedExpr, Constant, JoinedStr, FormattedValue, Call, Compare, YieldFrom, Yield, Await,
                  GeneratorExp, DictComp, SetComp, ListComp, Set, Dict, IfExp, Lambda, UnaryOp, BinOp, BoolOp, Slice,
                  Continue, Break, Pass, Expr, Nonlocal, Global, ImportFrom, Import, Assert, Try, Raise, AsyncWith,
                  With, If, While, AsyncFor, For, AnnAssign, AugAssign, Assign, Delete, Return, ClassDef,
                  AsyncFunctionDef, FunctionDef, Expression, Interactive, AST)
from typing import Any, cast
from collections import deque   # 双端队列

import pandas as pd

import sack.knowledge.kg_governor.pipeline_abstraction.Calls as Calls
from sack.knowledge.kg_governor.pipeline_abstraction.datatypes import GraphInformation
from sack.knowledge.kg_governor.pipeline_abstraction.Calls import File, pd_dataframe
from sack.knowledge.kg_governor.pipeline_abstraction.Calls.get_calls import get_calls
from sack.knowledge.kg_governor.pipeline_abstraction.util import is_file, ControlFlow, format_node_text, get_package
from sack.knowledge.kg_governor.pipeline_abstraction.ast_package import AstPackage, get_ast_package
from sack.knowledge.kg_governor.pipeline_abstraction.ast_package.types import CallComponents, CallArgumentsComponents, AssignComponents, BinOpComponents, AttributeComponents


def insert_parameter(parameters: dict, is_block: bool, parameter: str, value):
    if parameter is None:
        return
    if is_block:  # block函数需要多个参数值
        parameters[str(parameter)].append(value)
    else:
        parameters[str(parameter)] = value


# 由于整个自定义遍历方法中访问每个节点都没有使用generic_visit，因此visit遍历是很浅的（根节点下一层，也就是每个代码段）
class NodeVisitor(ast.NodeVisitor):  # NodeVisitor是遍历AST树的方法，这里用于自定义遍历方法
    graph_info: GraphInformation

    # TODO: REWORK VARIABLE NAMING
    def __init__(self, graph_information: GraphInformation = None):
        self.graph_info = graph_information
        self.columns = []  # 维护当前图节点用到的列
        self.files = {} # 维护记录所有用得到文件
        self.variables = {}  # 维护记录所有用到的变量
        self.alias = {} # 维护命名系统
        self.packages = {} # 维护使用到的函数包
        self.subgraph = {} # 维护嵌套的待访问子图
        self.subgraph_node = {}
        self.control_flow = deque() # 维护当前图节点的控制流（记录当前控制流的嵌套信息）
        self.user_defined_class = []
        self.working_file = {}
        self.target_node = None
        self.data_flow_container = {} # 维护整个代码涉及的数据流
        self.library_path = {}  # Save library path that can't be extrapolated. i.e. train_test_split

    def visit(self, node: AST) -> Any:  # 自动遍历整个node
        # 以这些节点类型为单位往图中添加节点（即这些类型一般都是非原子节点，可作为图的节点单元）
        if type(node) in [ast.Assign, ast.Import, ast.ImportFrom, ast.Expr, ast.For, ast.If,
                          ast.FunctionDef, ast.AugAssign, ast.Call, ast.Return, ast.Attribute]:  # TODO: Improve this
            self.columns.clear() # 每开辟到一个新的图节点都要重置该节点用的的列
            self.graph_info.add_node(format_node_text(node))  # 图中添加节点
            if len(self.control_flow) > 0: # 如果控制流不为空（因为它会记录一个控制流内部的访问过程，当控制流访问结束它也应该是空的），说明当前访问节点处在一个控制流中，图节点需要记录控制流信息
                self.graph_info.add_control_flow(self.control_flow)
            # data_flow是在遍历过程中维护的
        return super().visit(node)

    def visit_Interactive(self, node: Interactive) -> Any:
        pass

    def visit_Expression(self, node: Expression) -> Any:
        pass

    def visit_FunctionDef(self, node: FunctionDef) -> Any: # 访问到函数节点，则需要对其内部视为子图（子树）
        subgraph = SubGraph() # 函数节点是一个子图
        subgraph.graph_info = self.graph_info
        args = self.visit_arguments(node.args) # 访问参数节点获取到参数
        subgraph.arguments = {i: a for a in args for i in range(len(args))} # 函数参数就是子图参数
        subgraph.working_file = self.working_file

        self.subgraph[node.name] = subgraph  # 记录函数子图
        self.subgraph_node[node.name] = node # 记录函数节点
        # 并没有对子图visit，因为还未调用

    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef) -> Any:
        pass

    def visit_ClassDef(self, node: ClassDef) -> Any:
        pass

    def visit_Return(self, node: Return) -> Any:
        pass

    def visit_Delete(self, node: Delete) -> Any:
        pass

    def visit_Assign(self, node: Assign) -> Any:  # 访问赋值语句  等号两侧
        assign_components = AssignComponents()
        value_package = get_ast_package(node.value)  # node.value子节点元素，这里获取等号右侧的元素的处理方法
        value_package.extract_assign_value(self, node, assign_components)  # 调用visit_Attribute方法对右侧元素访问处理 （递归访问子节点，包括把用到的数据加入图中建立关联）

        variable = None  # TODO: Choose better name
        for target in node.targets:  # 左侧被赋值的变量
            target_package = get_ast_package(target) # 对等号左侧元素的处理方法
            variable = target_package.analyze_assign_target(self, target, assign_components) # 左侧变量的处理（也是递归访问子节点） variable是左侧变量的全称（components.path）

        if variable is not None and not isinstance(variable, list): # 不为空即有返回值 即target是下标类型，经历了下标递归处理 且不是list，是单个变量
            self._connect_node_to_column(self.files.get(variable))  # 左侧变量涉及的数据列加入图中

    def visit_AugAssign(self, node: AugAssign) -> Any:
        pass

    def visit_AnnAssign(self, node: AnnAssign) -> Any:
        pass

    def visit_For(self, node: For) -> Any: # for 要针对性的对子节点（子树）遍历
        if len(self.control_flow) == 0: # for属于控制流的一种  控制流没有记录说明当前遍历到了一个新的控制流的最外层节点，需要向图中添加for控制流模块
            self.graph_info.add_control_flow([ControlFlow.LOOP])
        fsg = ForSubGraph()
        # 配置子树信息（将节点信息同步过来）
        fsg.graph_info = self.graph_info
        fsg.working_file = self.working_file
        fsg.files = self.files.copy()
        fsg.variables = self.variables.copy()
        fsg.packages = self.packages
        fsg.alias = self.alias
        fsg.subgraph = self.subgraph
        fsg.subgraph_node = self.subgraph_node
        fsg.control_flow = self.control_flow.copy()
        fsg.control_flow.append(ControlFlow.LOOP) # 当前循环控制流要在控制流队列中记录
        fsg.data_flow_container = self.data_flow_container.copy()  # 数据流
        fsg.visit(node)  # 遍历子树

    def visit_AsyncFor(self, node: AsyncFor) -> Any:
        pass

    def visit_While(self, node: While) -> Any:
        pass

    def visit_If(self, node: If) -> Any:  # if条件  同样属于控制流  包含test（条件表达式）、body（为真时执行的语句块）和orelse（为假时执行的语句块）三个属性
        if len(self.control_flow) == 0: # 控制流为空说明访问到了一个新的控制流模块（处在最外层） 还没有添加到图中  所以要在图中添加该控制流模块
            self.graph_info.add_control_flow([ControlFlow.CONDITIONAL])
        self.control_flow.append(ControlFlow.CONDITIONAL)  # 记录当前控制流层级

        for el in node.body: # 遍历每个if为真时 每个要执行的语句
            self.visit(el)
        for el in node.orelse: # 遍历每个if为假时 每个要执行的语句
            self.visit(el)

        self.control_flow.pop() # 访问结束 控制流弹出 用于下次访问控制流时判断

    def visit_With(self, node: With) -> Any:
        pass

    def visit_AsyncWith(self, node: AsyncWith) -> Any:
        pass

    def visit_Raise(self, node: Raise) -> Any:
        pass

    def visit_Try(self, node: Try) -> Any:
        pass

    def visit_Assert(self, node: Assert) -> Any:
        pass

    def visit_Import(self, node: Import) -> Any: # import也属于控制流  import对象可能是library、class、function、package
        self.graph_info.add_control_flow([ControlFlow.IMPORT])  # import的控制流一定没有嵌套，当前控制流一定是空的，所以无需记录control_flow 直接记录import控制流模块
        for import_name in node.names: # 遍历每一个引入的内容
            name, as_name = self.visit_alias(import_name)  # 获取到内容名和自定义名称 这里的内容名是一个path  如引入matplotlib.pyplot包 自定义名称就是plt

            if as_name is not None:
                self.alias[as_name] = name  # 记录自定义名称和实际包名的映射

            self.graph_info.add_import_node(name) # 遍历该内容 要涉及遍历内容的所有依赖内容（用.分割的） 如matplotlib和matplotlib.pyplot  以及节点和library进行关联

    def visit_ImportFrom(self, node: ImportFrom) -> Any:  # from... import 类型 也属于控制流  和import相似
        self.graph_info.add_control_flow([ControlFlow.IMPORT])
        path = node.module # module就是from 和import之间的依赖内容全称

        for lib_name in node.names:  # 遍历每一个引入的内容
            name, as_name = self.visit_alias(lib_name)  # 访问该内容
            # 这里的name不是path而仅仅是name本身  如from matplotlib.pyplot import plot as plt  这里name就是plot  as_name就是plt
            if as_name is not None:
                self.alias[as_name] = name  # 记录name和别名映射
            self.graph_info.add_import_from_node(path, name) # 遍历该内容  具体实现时同样是取到name对应的path  然后归并到add_import_node对所有依赖内容进行处理
            self.library_path[name] = f'{path}.{name}'  # 拼接成path和内容映射

    def visit_Global(self, node: Global) -> Any:
        pass

    def visit_Nonlocal(self, node: Nonlocal) -> Any:
        pass

    def visit_Expr(self, node: Expr) -> Any:  # 表达式节点
        if isinstance(node.value, ast.Call):  # 如果子节点是函数调用就访问函数调用节点遍历
            self.visit_Call(node.value)
        elif isinstance(node.value, ast.Constant): # 常量无需遍历
            pass
        else:
            # print("EXPR VALUE:", node.__dict__)
            astor.to_source(node)  # 表达式转化为字符串代码，无特殊处理

    def visit_Pass(self, node: Pass) -> Any:
        pass

    def visit_Break(self, node: Break) -> Any:
        pass

    def visit_Continue(self, node: Continue) -> Any:
        pass

    def visit_Slice(self, node: Slice) -> Any:  # slice是特殊的下标Subscript类型
        lower = upper = step = None  # 切片操作的三要素 起始 终点 和间隔
        if isinstance(node.lower, ast.Constant):
            lower = self.visit_Constant(node.lower)  # 如果起始是常量，则解析其值
        # 为什么不处理终点和间隔

        return lower, upper, step

    def visit_BoolOp(self, node: BoolOp) -> Any:
        pass

    def visit_BinOp(self, node: BinOp) -> Any:  # 二元操作  如+-*/
        components = BinOpComponents()

        left_ast_package = get_ast_package(node.left)  # 运算符左侧元素处理工具
        left_ast_package.analyze_bin_op_branch(self, node, 'left', components)  # 对左侧元素处理

        right_ast_package = get_ast_package(node.right)
        right_ast_package.analyze_bin_op_branch(self, node, 'right', components) # 对右侧元素处理

        left_package = get_package(components.left, self.alias)  # 获取对左侧元素的方法的被调用信息 （这里的方法是指元素类型，如pandas.DataFrame）
        right_package = get_package(components.right, self.alias) # 获取右侧元素的方法的被调用信息

        if left_package is not None and right_package is not None:
            if left_package == pd_dataframe or right_package == pd_dataframe:  # 两侧变量类型都是DataFrame
                return f'{pd_dataframe.library_path}.{pd_dataframe.name}'  # 也就是pandas.DataFrame,直接返回两个变量的类型
            return astor.to_source(node) # 如果并非都是DataFrame 则返回二元操作本身的字符串代码
        elif left_package is not None and len(left_package.return_types) > 0: # 运算符右侧是空的  左侧变量的被调用方法的返回值不为空（表达左侧确实是有类型的变量）
            pack = left_package.return_types[0]
            return f"{pack.library_path}.{pack.name}"  # 返回内容为左侧变量的类型 （因为可运算类型一定相同）
        elif right_package is not None and len(right_package.return_types) > 0: # 运算符左侧是空的  右侧变量的被调用方法的返回值不为空
            pack = right_package.return_types[0]
            return f"{pack.library_path}.{pack.name}" # 返回内容为右侧变量的类型
        else:
            return format_node_text(node)  # 如果运算符左右两侧都是空的或者一边不为空但都没有返回值（表达其不是变量）  则节点转代码等待后续处理

    def visit_UnaryOp(self, node: UnaryOp) -> Any:
        pass

    def visit_Lambda(self, node: Lambda) -> Any:
        pass

    def visit_IfExp(self, node: IfExp) -> Any:
        pass

    def visit_Dict(self, node: Dict) -> Any: # 访问字典节点，key一般是常量直接获取值  value一般是嵌套结构，所以嵌套遍历获得
        keys = []
        values = []

        for key in node.keys:
            if isinstance(key, ast.Constant):  # 关键字是常量
                keys.append(self.visit_Constant(key)) # 访问获取常量值
            else:
                # print("DICT KEY:", node)
                astor.to_source(node)  # 不是常量是不正常情况，转字符串代码 后续处理

        for value in node.values:  # values其实返回的都是对应类型的"标量"（代表性内容，如变量就是变量名  属性就是属性path，函数调用就是基础库）
            if isinstance(value, ast.Constant): # 值是常量就访问常量获取值
                values.append(self.visit_Constant(value))
            elif isinstance(value, ast.Name): # 值是名字（变量名、函数名、类名）就访问名字（变量）
                values.append(self.visit_Name(value)) # 提取变量名
            elif isinstance(value, ast.Attribute): # 值是属性访问（如df.columns 这里columns就是df的属性）
                attr_value, _, _ = self.visit_Attribute(value) # 继续遍历属性节点
                values.append(attr_value)# 加入的是属性路径（path）
            elif isinstance(value, ast.List):  # 值是列表
                values.append(self.visit_List(value))# 实际值是列表里元素的"标量" （因为是递归获取）
            elif isinstance(value, ast.Call): # 值是函数调用
                _, _, _, base = self.visit_Call(value) # 遍历调用函数
                values.append(base) #  加入的实际值就是函数的parent_library  也就是value调用的函数的顶层库（如pandas）
            else:
                # print("DICT VALUE:", node.values)
                astor.to_source(node)

        return {a: b for a, b in tuple(zip(keys, values))}

    def visit_Set(self, node: Set) -> Any:
        pass

    def visit_ListComp(self, node: ListComp) -> Any:
        pass

    def visit_SetComp(self, node: SetComp) -> Any:
        pass

    def visit_DictComp(self, node: DictComp) -> Any:
        pass

    def visit_GeneratorExp(self, node: GeneratorExp) -> Any:
        pass

    def visit_Await(self, node: Await) -> Any:
        pass

    def visit_Yield(self, node: Yield) -> Any:
        pass

    def visit_YieldFrom(self, node: YieldFrom) -> Any:
        pass

    def visit_Compare(self, node: Compare) -> Any:  # 比较运算符（== < >）
        if isinstance(node.left, ast.Subscript): # 左侧是下标类型，递归访问下标类型
            self.visit_Subscript(node.left)
        elif isinstance(node.left, ast.Call): # 左侧是函数调用类型，递归访问函数调用
            self.visit_Call(node.left)
        else:
            # print("COMPARE LEFT:", node.__dict__)
            astor.to_source(node) # 只遍历这两种类型，其他类型暂不处理

        # 访问右侧比较项（可能有多个比较项，如a<b<c中，b和c都属于右侧比较项）
        for comparator in node.comparators:
            if isinstance(comparator, ast.Call): # 只遍历函数调用类型 其他不处理
                self.visit_Call(comparator)

    def _connect_node_to_column(self, file):  # 当前代码段访问到了某个数据集，这里通过node连接  把对应的数据列加入图中（也就是添加代码和数据集的映射）
        if file is None:
            return
        self.graph_info.add_columns(file.filename, self.columns)
        self.columns.clear() # 映射添加后就初始化清空columns

    def _extract_parent_package_information(self, components: CallComponents): # 补充被调用信息  以plt.show为例
        if components.package is None:
            return  # 函数完整路径为空就不用处理
        if isinstance(components.package, list):
            return # 函数完整路径是列表（有多个父包来源）也不处理

        components.extract_parent_library()  # 提取顶层包和剩余路径上的包   这里的顶层包可能是别名（plt），所以需要后续获取顶层包的实际路径path
        pkg = self.variables.get(components.parent_library) # 通过variables获取顶层包的信息(用别名映射到实际名称)  包含顶层包的实际path （matplotlib.pyplot）
        components.rewrite_library_path(pkg) # 用顶层包的实际path修正当前函数的完整路径 matplotlib.pyplot.show
        self._connect_node_to_column(self.files.get(components.parent_library))  # 连接函数代码和数据集的关联

    def visit_Call(self, node: Call) -> Any:  # 函数调用节点  是函数和数据关联的关键
        func_package: AstPackage
        func_package = get_ast_package(node.func) # 动态分析函数调用方式  用于递归处理函数子节点

        call_components = CallComponents() # 调用节点的相关信息
        func_package.extract_func(self, node, call_components) # 如果是函数名调用就访问Name即可  而如果是base.func调用，那base就有可能是变量，要涉及数据流存储和数据集映射

        self._extract_parent_package_information(call_components) # 补充调用节点的信息 主要是修正函数路径

        package_class = self._get_package_info(call_components.package) # 获取函数的被调用信息
        parameters = package_class.parameters.copy()  # 获取函数的参数
        args_components = CallArgumentsComponents(package_class.parameters.keys())  # 获取函数涉及的参数的节点信息 （通过涉及的参数名实例化）


        # 处理位置参数:不标定参数名的参数值赋值方式  如func(1,2)
        for i in range(len(node.args)):
            # 检测参数是否存在block参数（可变参数，list dict等可迭代对象，如*args ）
            if not args_components.is_block: # 如果函数的参数不是block就继续遍历各个参数，直到遍历完成或检测到一个block参数
                args_components.next_label() # label迭代到下一个参数名
                args_components.set_is_block(parameters) # 如果label指示的参数包含"*"那就是block，就要把is_block置为true  也就是说明当前参数中存在block参数

            # 对每个参数处理
            args_package = get_ast_package(node.args[i])
            parameter_value = args_package.analyze_call_arguments(self, node, args_components, call_components, i) # 递归访问该参数（返回参数值）

            # 对参数名值映射
            if package_class.is_relevant:# 如果调用的是库函数
                insert_parameter(parameters, args_components.is_block, args_components.label, parameter_value) # 将参数名和参数值做映射 存储在parameters中

        # 处理关键字参数:标定参数名的赋值表达式的赋值方式  如func(a=1,b=2)
        for kw in node.keywords:
            if isinstance(kw, ast.keyword):
                edge, value = self.visit_keyword(kw) # 获取参数名和值
                self._extract_dataflow(value)  # 实际调用时会涉及数据流 因此要提取并记录数据流 （因为value可能是之前的某个变量）
                self._add_to_column(value, call_components.base_package)  # 还要往visitor中添加数据集 用于后续做变量和数据的映射
                if package_class.is_relevant and edge is not None:
                    parameters[edge] = str(value)  # 同样存储到parameters中

        self.graph_info.add_parameters(parameters)  # 把函数调用涉及到的所有参数添加到图中（这里就是函数的参数和实际dataset字段之间的映射边）
        self._create_package_call(package_class, call_components.package) # 函数和库映的映射也添加到图中（library和pipeline的映射边）

        if call_components.base_package is not None:
            variable, *_ = call_components.base_package.split('.') # 获取名义顶层包  也就是plt
            self._connect_node_to_column(self.files.get(variable)) # 连接函数和数据集的关联


        # 如果调用的是自定义函数（遍历子树节点）
        if type(call_components.package) != list and call_components.package in self.subgraph.keys(): # 如果调用函数的完整路径唯一（不是列表） 且函数节点的子图中存在（函数有定义）
            # 函数被调用时遍历函数子树
            return_type = self._subgraph_logic(call_components.package,  # 触发内部的递归函数的遍历
                                               args_components.file_args,
                                               args_components.call_args)
            return return_type, call_components.file, call_components.package, call_components.base_package  # 返回函数返回值类型，调用涉及的文件，函数完整路径，函数的基类包
        elif package_class.is_relevant: # 如果调用的是库包里的函数
            return (package_class.return_types, # 从库信息中找到返回值类型
                    call_components.file, # 同样的调用涉及的文件，完整路径和基路径
                    call_components.package,
                    call_components.base_package)
        return [], call_components.file, call_components.package, call_components.base_package # 其他情况

    def visit_FormattedValue(self, node: FormattedValue) -> Any:
        pass

    def visit_JoinedStr(self, node: JoinedStr) -> Any:
        pass

    def visit_Constant(self, node: Constant) -> Any:
        return node.value

    def visit_NamedExpr(self, node: NamedExpr) -> Any:
        pass

    def visit_Attribute(self, node: Attribute) -> Any:  # 通用的访问node的处理 （一般会递归调用，遍历整个子树）
        components = AttributeComponents()  # 记录递归访问时每一层的node的信息  包括path（当前节点地址）、parent_path（父节点地址）和file
        attribute_package = get_ast_package(node.value) # node.value指node的子节点   取到对应元素的处理方法（对子节点的处理方法）
        attribute_package.analyze_attribute_value(self, node, components) # 递归访问子树（不断访问node.value.value...）并改变当前层node的信息components
        return components.path, components.parent_path, components.file  # 返回当前node的信息

    def visit_Subscript(self, node: Subscript) -> Any:  # 访问下标元素
        value_package = get_ast_package(node.value) # 获取子节点处理工具  顺便判断子节点类型（这里子节点就是下标的主体如df["col"]的df）
        name, base = value_package.extract_subscript_value(self, node) # 递归处理子节点 返回主体的path和主体  涉及递归访问主体的attribute （visit_Attribute）  这里的name就是主体的path base是主题的base path

        # 访问主体的下标元素
        if not isinstance(name, list):   # 主体不能有多个路径来源
            var = self.variables.get(name, self.variables.get(base)) # 找到主体的实际名 如df对应DataFrame
            file = self.files.get(name, self.files.get(base)) # 取到主体对应的数据集
            if var is pd_dataframe and file is not None:  # 如果发现主体就是dataframe 而且 有相关的数据集
                working_file = self.working_file.get(file.filename, pd.DataFrame()) # 取到主体映射的数据集
                if isinstance(node.slice, ast.Index): # 如果下标是index
                    index = self.visit_Index(node.slice) # 递归遍历下标获取下标值
                    column_list = list(working_file) # 返回的数据集就是list(columns）  （这里是列名列表）

                    if not isinstance(index, list): # index是单个值 可能是变量 就获取变量对应的值  就是实际的下标值
                        index = self.variables.get(index, index)
                    if isinstance(index, int): # 如果是index 是 int  说明index取到了下标值
                        if index < len(column_list): # 确保被操作数据不越界
                            column = column_list[index] # 取到对应列名
                            self.columns.append(column) # 添加到columns  标识用到的列  用于后续处理
                    elif isinstance(index, str) and index in column_list: #index是字符串  那就是df["columns_name"]的方式 那index其实就是列名
                        self.columns.append(index) # 直接添加列名即可
                    elif isinstance(index, list): # 取到的index实际值是列表  那就是多个列名
                        for value in index:
                            if value in column_list:
                                self.columns.append(value) # 把多个列名添加进columns
                elif isinstance(node.slice, ast.ExtSlice):  #  扩展索引 多维切片  即二维[0:2, 1:3]
                    self.visit_ExtSlice(node.slice)  # TODO: HOW TO EXPRESS THIS VALUE? # 嵌套递归
                elif isinstance(node.slice, ast.Slice):# 范围切片  索引是二元甚至三元的切片  [i:j] [i:j:k]
                    lower, upper, step = self.visit_Slice(node.slice) # 获取三元组  取对应列
                    columns = list(working_file)
                    if lower is None:
                        lower = 0
                    if upper is None:
                        upper = len(columns)
                    if step is None:
                        step = 1
                    if isinstance(lower, int):
                        for i in range(lower, upper, step):
                            self.columns.append(columns[i])
                    elif isinstance(lower, str):# start index是变量  所以切片索引是字符串匹配的
                        is_checked = False
                        for col in columns:
                            if is_checked:
                                self.columns.append(col)
                                if col == upper: # 匹配列直到upper结束
                                    break
                            else:
                                if col == lower: # 开始匹配列
                                    self.columns.append(col)
                                    is_checked = True
                else:
                    # print('SUBSCRIPT SOMETHING', node.slice, node.__dict__)
                    astor.to_source(node)  # 异常情况，等待后续处理
                self._connect_node_to_column(file)  # 节点和数据连接（代码连接操作）
        return name, base

    def visit_Starred(self, node: Starred) -> Any:
        pass

    def visit_Name(self, node: Name) -> Any:
        return node.id

    def visit_List(self, node: List) -> Any:
        elements = []
        for i in range(len(node.elts)):  # 对列表内的不同类型元素递归访问
            element_package = get_ast_package(node.elts[i])
            element_package.extract_list_element(self, node, i, elements)

        return elements

    def visit_Tuple(self, node: Tuple) -> Any:# 这里针对不同类型遍历，并将返回的各种元素的核心添加到列表中一同返回
        elements = []
        for element in node.elts:  # elts是所有元素（子节点）构成的列表  ctx是元组被使用的方式（load store del）
            if isinstance(element, ast.Name):
                elements.append(self.visit_Name(element))
            elif isinstance(element, ast.Constant):
                elements.append(self.visit_Constant(element))
            elif isinstance(element, ast.Subscript):
                name, _ = self.visit_Subscript(element)
                elements.append(name)
            elif isinstance(element, ast.Call):
                _, _, _, base = self.visit_Call(element)
                elements.append(base)
            else:
                # print("TUPLE ELTS:", node.__dict__)
                astor.to_source(node)
        return elements

    def visit_Del(self, node: Del) -> Any:
        pass

    def visit_Load(self, node: Load) -> Any:
        pass

    def visit_Store(self, node: Store) -> Any:
        pass

    def visit_And(self, node: And) -> Any:
        pass

    def visit_Or(self, node: Or) -> Any:
        pass

    def visit_Add(self, node: Add) -> Any:
        pass

    def visit_BitAnd(self, node: BitAnd) -> Any:
        pass

    def visit_BitOr(self, node: BitOr) -> Any:
        pass

    def visit_BitXor(self, node: BitXor) -> Any:
        pass

    def visit_Div(self, node: Div) -> Any:
        pass

    def visit_FloorDiv(self, node: FloorDiv) -> Any:
        pass

    def visit_LShift(self, node: LShift) -> Any:
        pass

    def visit_Mod(self, node: Mod) -> Any:
        pass

    def visit_Mult(self, node: Mult) -> Any:
        pass

    def visit_MatMult(self, node: MatMult) -> Any:
        pass

    def visit_Pow(self, node: Pow) -> Any:
        pass

    def visit_RShift(self, node: RShift) -> Any:
        pass

    def visit_Sub(self, node: Sub) -> Any:
        pass

    def visit_Invert(self, node: Invert) -> Any:
        pass

    def visit_Not(self, node: Not) -> Any:
        pass

    def visit_UAdd(self, node: UAdd) -> Any:
        pass

    def visit_USub(self, node: USub) -> Any:
        pass

    def visit_Eq(self, node: Eq) -> Any:
        pass

    def visit_Gt(self, node: Gt) -> Any:
        pass

    def visit_GtE(self, node: GtE) -> Any:
        pass

    def visit_In(self, node: In) -> Any:
        pass

    def visit_Is(self, node: Is) -> Any:
        pass

    def visit_IsNot(self, node: IsNot) -> Any:
        pass

    def visit_Lt(self, node: Lt) -> Any:
        pass

    def visit_LtE(self, node: LtE) -> Any:
        pass

    def visit_NotEq(self, node: NotEq) -> Any:
        pass

    def visit_NotIn(self, node: NotIn) -> Any:
        pass

    def visit_comprehension(self, node: comprehension) -> Any:
        pass

    def visit_ExceptHandler(self, node: ExceptHandler) -> Any:
        pass

    def visit_arguments(self, node: arguments) -> Any:  # 访问函数参数列表，返回参数名列表
        arguments_list = []
        for argument in node.args:
            arguments_list.append(self.visit_arg(argument))
        return arguments_list

    def visit_arg(self, node: arg) -> Any: # 访问单个参数
        return node.arg # arg是参数名

    def visit_keyword(self, node: keyword) -> Any:  # 函数调用的关键字参数  如a=1 用于解析参数名a和参数值1
        keyword_package = get_ast_package(node.value)
        value = keyword_package.extract_keyword_value(self, node) # 根据关键字值的类型访问
        return node.arg, value  # 返回参数名和参数值（值可能是变量 常量 函数等 value也就是变量名 常量 函数名等）

    def visit_alias(self, node: alias) -> Any:  # 别名就是返回原名和别名
        return node.name, node.asname

    def visit_withitem(self, node: withitem) -> Any:
        pass

    def visit_ExtSlice(self, node: ast.ExtSlice) -> Any:  # 针对扩展切片（多维切片）的处理 如[1:2,1:4]
        for dim in node.dims: # 对不同的维度分别遍历
            sl = None
            if isinstance(dim, ast.Slice): # 嵌套一维普通切片
                lower, upper, step = self.visit_Slice(dim)
            elif isinstance(dim, ast.Index): # 如果某个维度是index切片 就直接嵌套访问index节点
                sl = self.visit_Index(dim)
            else:
                # print("EXT_SLICE DIM:", node.__dict__)
                astor.to_source(node)
        pass

    def visit_Index(self, node: ast.Index) -> Any:
        if isinstance(node.value, ast.Constant):# 索引是常量  如5 "col"等
            return self.visit_Constant(node.value)
        elif isinstance(node.value, ast.BinOp):  # 索引是二元表达式 如 x+2
            self.visit_BinOp(node.value)
        elif isinstance(node.value, ast.Compare): # 索引是比较表达式 如 x>5
            self.visit_Compare(node.value)
        elif isinstance(node.value, ast.List): # 索引是列表
            return self.visit_List(node.value)
        elif isinstance(node.value, ast.Subscript): # 索引是下标（没有设计好）
            pass
            # print(self.visit_Subscript(node.value))  # TODO: MAKE SOMETHING OF THIS VALUE
        elif isinstance(node.value, ast.Name): # 索引是变量
            return self.visit_Name(node.value)
        else:
            # print("INDEX VALUE:", node.__dict__)
            astor.to_source(node)

    def visit_Suite(self, node: ast.Suite) -> Any:
        pass

    def visit_AugLoad(self, node: ast.AugLoad) -> Any:
        pass

    def visit_AugStore(self, node: ast.AugStore) -> Any:
        pass

    def visit_Param(self, node: ast.Param) -> Any:
        pass

    def visit_Num(self, node: ast.Num) -> Any:
        pass

    def visit_Str(self, node: ast.Str) -> Any:
        pass

    def visit_Bytes(self, node: ast.Bytes) -> Any:
        pass

    def visit_NameConstant(self, node: ast.NameConstant) -> Any:
        pass

    def visit_Ellipsis(self, node: Ellipsis) -> Any:
        pass

    def _add_to_column(self, column_name, table_name=None): # 获取数据集中对应的列 添加到visitor维护的columns用于后续与数据集映射
        file = self.files.get(table_name, File(''))
        file_name = file.filename
        working_file = self.working_file.get(file_name, pd.DataFrame())
        if column_name in list(working_file):
            self.columns.append(column_name)
            return True
        return False

    def _subgraph_logic(self, package, file_args, call_args):  # call访问函数子图（自定义函数）的逻辑  package是被调用的函数 file_args是涉及的文件类参数  call_args是涉及的其他参数
        s_graph = self.subgraph.get(package)
        s_graph.data_flow_container = self.data_flow_container.copy()

        for param in s_graph.arguments.values(): # 对于自定义函数的所有参数名  在数据流中建立所有参数与当前数据流终点的映射（因为函数内部可能会有这些参数和数据的交互 也就是数据流）
            s_graph.data_flow_container[param] = self.graph_info.tail

        s_graph.files = {s_graph.arguments.get(file_k): self.files.get(file_args.get(file_k))  # 传递文件
                         for file_k in file_args.keys()}
        s_graph.variables = {s_graph.arguments.get(arg_k): self.variables.get(call_args.get(arg_k)) # 传递变量
                             for arg_k in call_args.keys()}
        s_graph.is_starting = True
        s_graph.visit(self.subgraph_node.get(package)) # 嵌套访问
        return s_graph.return_type

    def param_subgraph_init(self): # 参数子图的初始化
        psg = ParamSubGraph()
        psg.graph_info = self.graph_info
        psg.working_file = self.working_file
        psg.files = self.files
        psg.variables = self.variables
        psg.packages = self.packages
        psg.alias = self.alias
        psg.data_flow_container = self.data_flow_container
        psg.library_path = self.library_path
        return psg

    def _create_package_call(self, package_class, package):  # 包被调用的处理
        if package_class.is_relevant: # 如果调用的是库包里的函数
            self.graph_info.add_package_call(package_class.full_path()) # 触发import节点
        elif isinstance(package, str) and package in ("len", "range", "list"): # 调用的是默认python包
            self.graph_info.add_built_in_call(package)# 触发import节点

    def _file_creation(self, file: str) -> File:
        if is_file(file): # 检测到是csv文件
            _, filename = os.path.split(file)
            file = File(filename)
            self.graph_info.add_file(file) # 记录该数据文件
            return file

    def _extract_dataflow(self, variable_name):  # 提取并记录该变量的数据流
        if not isinstance(variable_name, str): # 变量名不是字符串
            return
        flow = self.data_flow_container.get(variable_name) # 提取当前该变量的数据流
        if flow is not None:
            self.graph_info.add_data_flows(flow)  # 在图上添加该变量的数据流

    def _create_library_path(self, package_name): # 修改包路径
        if not package_name or isinstance(package_name, list):
            return ''
        if '.' in package_name:
            base, *rest = package_name.split('.') # 获取顶层包和后续路径
            base = self.alias.get(base, base) # 获取顶层包的实际名
            return f'{base}.{".".join(rest)}' # 修正路径pyplot.show
        return self.library_path.get(package_name, package_name) # 其他情况直接返回未解析的函数的路径

    def _get_package_info(self, package_name): # 根据修正的包路径获取包信息
        library_path = self._create_library_path(package_name)
        # return packages.get(library_path, Calls.Call(is_relevant=False))
        package = get_calls(library_path)
        return package


class SubGraph(NodeVisitor):  # 函数子图遍历逻辑，继承自代码的抽象语法树遍历逻辑
    __slots__ = ['arguments', 'is_starting', 'return_type']

    def __init__(self):
        super().__init__()
        self.is_starting = True
        self.return_type = None

    def visit(self, node: AST) -> Any: # visit就是访问函数节点
        if self.is_starting: # 初始状态，访问函数体节点  开始递归遍历
            self.is_starting = False
            return self.visit_FunctionDef(cast(ast.FunctionDef, node))
        return super().visit(node)

    def visit_FunctionDef(self, node: FunctionDef) -> Any:  # 递归访问函数体
        self.control_flow.append(ControlFlow.METHOD) # 函数属于控制流 需要在控制流记录层级   通过入栈出栈的方式记录嵌套层级
        for el in node.body: # 嵌套遍历函数体的每个语句
            self.visit(el)
        self.control_flow.pop()

    def visit_Return(self, node: Return) -> Any:  # 访问函数返回节点
        if isinstance(node.value, ast.Call):  # 返回函数调用 则嵌套函数调用节点
            self.visit_Call(node.value)
        elif isinstance(node.value, ast.Name): # 返回变量 则访问变量
            name = self.visit_Name(node.value)
            var = self.variables.get(name) # 获取变量的原名
            if var is not None and isinstance(var, Calls.Call): # 获取变量被调用的信息  将返回类型置为变量的返回类型
                self.return_type = var.return_types
        else:
            # print("SUBGRAPH RETURN VALUE:", node.__dict__)
            astor.to_source(node)


class ParamSubGraph(NodeVisitor):  # 参数构成的子图  target_node是使用该参数的节点
    __slots__ = ['return_type', 'target_node']

    def __init__(self):
        super().__init__()
        self.return_type = None

    def visit(self, node: AST) -> Any:
        n = super().visit(node)
        # 找到用到该参数的节点，把访问参数的逻辑放在使用参数之前 （通过调整图中的节点顺序实现）
        if self.target_node is None: # 如果不知道参数所在函数的位置
            self.graph_info.rewrite_node_flow()  # 交换最后两个节点的顺序（默认函数和参数是当前图的最后两个节点）
        else:
            self.graph_info.insert_before(self.target_node) # 去掉尾节点添加到目标节点前边
        return n

    def visit_Call(self, node: Call) -> Any:  # TODO: REMOVE UNUSED ELEMENT
        return_types, file, name, base = super().visit_Call(node)
        return_types = return_types if return_types is not None else []
        info = None
        # if package is not None:
        #     *path, lib = package.split('.')
        #     info = get_package(lib, '.'.join(path))
        if info is not None:
            self.return_type = return_types[0] if len(return_types) > 0 else None
        self.return_type = return_types
        return return_types, file, name, base

#  for循环的访问只涉及一轮 因为循环本身逻辑是固定的  变化的只是迭代变量的取值  所以访问子树也只会访问一轮
class ForSubGraph(NodeVisitor): # for循环体组成的子图
    def __init__(self):
        super().__init__()
        self.is_starting = True

    def visit(self, node: AST) -> Any: # 访问for节点
        if self.is_starting:
            return self.visit_For(cast(ast.For, node)) # 初始访问for语句
        return super().visit(node) # 循环访问循环主体的语句

    def visit_For(self, node: For) -> Any:
        if self.is_starting: # 访问for迭代语句
            self.is_starting = False
            target = iter_value = None
            if isinstance(node.target, ast.Name):  # 取到的for i ... 的i如果是变量 就访问变量
                target = self.visit_Name(node.target)
            else:
                # print("FOR TARGET", node.__dict__)
                astor.to_source(node)

            # 取到迭代对象 for i in list 的list
            if isinstance(node.iter, ast.Call): # 如果是函数调用 就嵌套访问调用函数节点
                self.visit_Call(node.iter)
            elif isinstance(node.iter, ast.Name): # 是变量就访问变量
                iter_value = self.visit_Name(node.iter)
            elif isinstance(node.iter, ast.List): # 是list就访问list并把list里的元素（i）和list里元素的实际名称做映射
                self.variables[target] = self.visit_List(node.iter)
            else:
                # print("FOR ITER:", node.__dict__)
                astor.to_source(node)

            if iter_value in self.variables.keys(): # 如果迭代元素本身是变量 在variables里有记录（是之前用到的已有变量） 就把i和迭代元素对齐
                self.variables[target] = self.variables.get(iter_value)

            for el in node.body: # 访问函数体每个语句
                self.visit(el)
        else:  # 感觉永远不会出现这种情况  因为单个for循环的self.visit_For只会执行一次  并列或嵌套的for循环会开辟一个新的for遍历节点，不会依赖其他for子图里的self.is_starting
            super().visit_For(node)
