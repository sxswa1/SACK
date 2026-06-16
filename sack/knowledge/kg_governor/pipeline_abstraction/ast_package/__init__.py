### 元素的处理方法定义

import ast
import astor
from typing import cast

import sack.knowledge.kg_governor.pipeline_abstraction.Calls as Calls
from sack.knowledge.kg_governor.pipeline_abstraction.Calls.get_calls import get_calls
from sack.knowledge.kg_governor.pipeline_abstraction.util import format_node_text
from sack.knowledge.kg_governor.pipeline_abstraction.ast_package.types import CallComponents, CallArgumentsComponents, AssignComponents, BinOpComponents, \
    AttributeComponents


class AstPackage:
    def extract_func(self, node_visitor: ast.NodeVisitor, node: ast.Call, components: CallComponents):
        # print("CALL FUNC:", node.__dict__)
        astor.to_source(node)

    def analyze_call_arguments(self, node_visitor: ast.NodeVisitor, node: ast.Call, components: CallArgumentsComponents,
                               call_components: CallComponents, pos: int):
        # print("CALL ARG:", node.__dict__)
        astor.to_source(node)

    def extract_assign_value(self, node_visitor: ast.NodeVisitor, node: ast.Assign, components: AssignComponents):
        # print("ASSIGN VALUE:", node.__dict__)
        astor.to_source(node)

    def analyze_assign_target(self, node_visitor: ast.NodeVisitor, node: ast, components: AssignComponents):
        # print("ASSIGN TARGET:", node.__dict__)
        astor.to_source(node)

    def extract_keyword_value(self, node_visitor: ast.NodeVisitor, node: ast):
        # print("KEYWORD VALUE:", node.__dict__)
        pass

    def extract_list_element(self, node_visitor: ast.NodeVisitor, node: ast.List, pos: int, list_elements: list):
        # print("LIST VALUE:", node.__dict__)
        astor.to_source(node)

    def analyze_bin_op_branch(self, node_visitor: ast.NodeVisitor, node: ast.BinOp, side: str, components: BinOpComponents):
        # print(f"BinOp {side.upper()} BRANCH VALUE:", node.__dict__)
        astor.to_source(node)

    def extract_subscript_value(self, node_visitor: ast.NodeVisitor, node: ast.Subscript):
        # print("SUBSCRIPT VALUE", node.__dict__)
        astor.to_source(node)
        return None, None

    def analyze_attribute_value(self, node_visitor: ast.NodeVisitor, node: ast.Attribute,
                                components: AttributeComponents):
        # print("ATTRIBUTE VALUE:", node.__dict__)
        astor.to_source(node)


class Name(AstPackage):  # 变量名
    def extract_func(self, node_visitor: ast.NodeVisitor, node: ast.Call, components: CallComponents):
        components.package = node_visitor.visit_Name(cast(ast.Name, node.func)) # 如果是函数直接调用（直接func的方式调用） 就继续访问函数名子节点即可

    def analyze_call_arguments(self, node_visitor: ast.NodeVisitor, node: ast.Call, components: CallArgumentsComponents,
                               call_components: CallComponents, pos: int):
        parameter_value = node_visitor.visit_Name(cast(ast.Name, node.args[pos]))
        node_visitor._extract_dataflow(parameter_value)
        node_visitor._add_to_column(parameter_value, call_components.base_package)

        if parameter_value in node_visitor.files.keys():
            call_components.file = node_visitor.files.get(parameter_value)
            components.file_args[pos] = parameter_value
        if parameter_value in node_visitor.variables.keys():
            components.call_args[pos] = parameter_value
            variable = node_visitor.variables.get(parameter_value)
            if isinstance(variable, list):
                for col_value in variable:
                    node_visitor._add_to_column(col_value, call_components.base_package)
                    call_components.file = node_visitor._file_creation(col_value)
                    if not isinstance(col_value, list) and col_value in node_visitor.files.keys():
                        call_components.file = node_visitor.files.get(col_value)
                        components.file_args[pos] = col_value

        return parameter_value

    def extract_assign_value(self, node_visitor: ast.NodeVisitor, node: ast.Assign, components: AssignComponents):
        components.value = node_visitor.visit_Name(cast(ast.Name, node.value))

    def analyze_assign_target(self, node_visitor: ast.NodeVisitor, node: ast, components: AssignComponents): # 赋值语句等号左侧变量的处理
        name = node_visitor.visit_Name(node) # 访问左侧目标变量
        node_visitor.data_flow_container[name] = node_visitor.graph_info.tail  # 记录数据流，就是记录左侧变量和右边表达式之间的映射关系（图的tail就是当前遍历的节点）
        if type(components.value) == str:  # 赋值语句右侧是字符串（单个表达式）
            if components.file is not None: # 如果赋值语句的file字段不为空（也就是赋值语句有用到文件）
                node_visitor.files[name] = components.file  # 把赋值语句用到的文件添加到当前节点遍历记录的文件 （用于分析时使用，如连接columns）
            elif components.value in node_visitor.files.keys():# 如果赋值语句没有用到文件，但visitor保存过右侧表达式对应的文件（之前在其他地方访问过相同的表达式）
                node_visitor.files[name] = node_visitor.files.get(components.value) # 把之前相同表达式用的的文件同步到左侧变量
            if components.value in node_visitor.variables.keys(): # 如果右侧表达式曾和某个变量有映射关系
                node_visitor.variables[name] = node_visitor.variables.get(components.value) # 把右侧表达式对应的变量同步到左侧变量（因为左侧变量和右侧表达式等价，所以右侧表达式的映射也可以同步到左侧变量）
        elif isinstance(components.value, list): # 赋值语句右侧是列表（多个表达式？）
            if len(components.value) > 0: # 右侧表达式不为空
                node_visitor.variables[name] = components.value[0]# 右侧第一个表达式映射到左侧变量
            if components.file is not None: # 赋值语句有用到文件（也就是当前右侧表达式有用到文件）
                node_visitor.files[name] = components.file  # 文件映射到左侧变量

    def extract_keyword_value(self, node_visitor: ast.NodeVisitor, node: ast):
        return node_visitor.visit_Name(node.value)

    def extract_list_element(self, node_visitor: ast.NodeVisitor, node: ast.List, pos: int,  list_elements: list):
        list_elements.append(node_visitor.visit_Name(cast(ast.Name, node.elts[pos])))

    def analyze_bin_op_branch(self, node_visitor: ast.NodeVisitor, node: ast.BinOp, side: str, components: BinOpComponents): # 在name场景下的二元被操作元素（即被操作元素是变量）
        name = node_visitor.visit_Name(getattr(node, side)) # 访问一侧的变量名
        node_visitor._extract_dataflow(name) # 追踪该变量的数据流  提取并添加到图上

    def extract_subscript_value(self, node_visitor: ast.NodeVisitor, node: ast.Subscript):
        return node_visitor.visit_Name(cast(ast.Name, node.value)), None

    def analyze_attribute_value(self, node_visitor: ast.NodeVisitor, node: ast.Attribute,
                                components: AttributeComponents):
        value = node_visitor.visit_Name(cast(ast.Name, node.value))
        is_column = node_visitor._add_to_column(node.attr, value)
        package = node_visitor.variables.get(value)  # TODO: Makes variables all packages

        if isinstance(package, str):
            components.path = f"{package}{'' if is_column else f'.{node.attr}'}"
            components.parent_path = value
        elif isinstance(package, list):
            components.path = [f"{el}{'' if is_column else f'.{node.attr}'}" for el in package]
            components.parent_path = value
        elif type(package) in (int, float):
            components.parent_path = value
        elif package is not None:
            components.path = f"{package.library_path}.{package.name}{'' if is_column else f'.{node.attr}'}"
            components.parent_path = value
        else:
            components.path = f"{value}.{node.attr}"
            components.parent_path = value


class Attribute(AstPackage): # attribute类元素的处理方法（属性访问） 如df.columns df.columns.values    具有value（被操作对象）、attr（操作本身）和ctx（操作类型）三个部分（ctx是操作类型，如load加载（用于赋值）、store存储（被赋值）、del删除（被删除）  columns values就属于load）
    def extract_func(self, node_visitor: ast.NodeVisitor, node: ast.Call, components: CallComponents):
        components.package, components.base_package, components.file = node_visitor.visit_Attribute(cast(ast.Attribute, node.func)) # 如果是属性方式访问函数，则表明可能调用方式为"base.func"的方式，得视为属性进行遍历（要分析其base）

        # 属性访问方式调用就很有可能涉及数据流变化（如base是变量df时） 所以要进行数据流以及数据集连接操作
        node_visitor._extract_dataflow(components.base_package)
        f = node_visitor.files.get(components.base_package) #
        node_visitor._connect_node_to_column(f)

    def extract_assign_value(self, node_visitor: ast.NodeVisitor, node: ast.Assign, components: AssignComponents):
        components.value, base, components.file = node_visitor.visit_Attribute(cast(ast.Attribute, node.value))  # 进一步递归访问右侧表达式（嵌套处理，为什么不用self.generic_visit触发子遍历）
        # 这里根节点（AssignNode）的path直接沿用等号右侧表达式的path(AttributeNode)  parent_path则是拿到右侧表达式的parent_path后（因为是跨层直接传递，也就是最底层节点的parent_path，很有可能就是df的地址，也就是用到的数据的地址）
        node_visitor._connect_node_to_column(node_visitor.files.get(base))  # 这里就相当于获取到当前赋值语句右侧被操作文件的地址了

    def extract_keyword_value(self, node_visitor: ast.NodeVisitor, node: ast):  # 关键字的值是属性
        value, _, _ = node_visitor.visit_Attribute(node.value)
        return value

    def extract_subscript_value(self, node_visitor: ast.NodeVisitor, node: ast.Subscript):
        name, base, _ = node_visitor.visit_Attribute(cast(ast.Attribute, node.value)) # 嵌套attribute访问（因为当前节点的子节点是attribute）
        try:
            if name is not None and isinstance(name, str):
                call = get_calls(name)
                package = call if call.call_type else None
                name = package.return_types[0].full_path()
        finally:
            return name, base

    def analyze_attribute_value(self, node_visitor: ast.NodeVisitor, node: ast.Attribute, # 分析变量值
                                components: AttributeComponents):
        path, components.parent_path, components.file = node_visitor.visit_Attribute(cast(ast.Attribute, node.value)) # 递归访问变量，访问node.value   这里components的parent_path和file都是随层级直接传递 没有变化（底层和跟的对应字段相同）

        components.path = f"{path}.{node.attr}" # components.path是当前节点node的attr的地址 以df.columns.values举例  最底层的attr是df,compnents.path是df  往上一层是columns，df.columns 再往上就是values,df.columns.values


class Constant(AstPackage): # 常量
    def analyze_call_arguments(self, node_visitor: ast.NodeVisitor, node: ast.Call, components: CallArgumentsComponents,
                               call_components: CallComponents, pos: int):
        parameter_value = node_visitor.visit_Constant(cast(ast.Constant, node.args[pos]))

        if call_components.file:
            return parameter_value

        node_visitor._add_to_column(parameter_value, call_components.base_package)
        call_components.file = node_visitor._file_creation(parameter_value)

        if parameter_value in node_visitor.files.keys():
            call_components.file = node_visitor.files.get(parameter_value)
            components.file_args[pos] = parameter_value
        if parameter_value in node_visitor.variables.keys():
            components.call_args[pos] = parameter_value
        if call_components.package in node_visitor.user_defined_class:
            components.class_args.append(parameter_value)

        return parameter_value

    def extract_assign_value(self, node_visitor: ast.NodeVisitor, node: ast.Assign, components: AssignComponents):
        components.value = node_visitor.visit_Constant(cast(ast.Constant, node.value))
        components.file = node_visitor._file_creation(components.value)

    def extract_keyword_value(self, node_visitor: ast.NodeVisitor, node: ast): # 关键字的值是常量
        return node_visitor.visit_Constant(node.value)

    def extract_list_element(self, node_visitor: ast.NodeVisitor, node: ast.List, pos: int,  list_elements: list):
        list_elements.append(node_visitor.visit_Constant(cast(ast.Constant, node.elts[pos])))

    def analyze_bin_op_branch(self, node_visitor: ast.NodeVisitor, node: ast.BinOp, side: str, components: BinOpComponents):  # 如果二元运算的是常量
        node_visitor.visit_Constant(getattr(node, side))  # 访问常量获取到常量值
        setattr(components, side, None)  # 如果是常量，就把相关信息


class Call(AstPackage): # 函数调用
    def analyze_call_arguments(self, node_visitor: ast.NodeVisitor, node: ast.Call, components: CallArgumentsComponents,
                               call_components: CallComponents, pos: int):
        psg = node_visitor.param_subgraph_init()
        psg.subgraph_node = node_visitor.subgraph_node
        psg.subgraph = node_visitor.subgraph
        psg.visit(node.args[pos])

        if psg.return_type is None:
            return None
        if len(psg.return_type) == 1:
            return psg.return_type[0].name
        return [psg.return_type[i].name for i in range(len(psg.return_type))]

    def extract_assign_value(self, node_visitor: ast.NodeVisitor, node: ast.Assign, components: AssignComponents):
        components.value, components.file, _, _ = node_visitor.visit_Call(cast(ast.Call, node.value))

    def extract_keyword_value(self, node_visitor: ast.NodeVisitor, node: ast):
        _, _, _, base = node_visitor.visit_Call(cast(ast.Call, node.value))
        return base

    def extract_list_element(self, node_visitor: ast.NodeVisitor, node: ast.List, pos: int,  list_elements: list):
        package, file, name, _ = node_visitor.visit_Call(cast(ast.Call, node.elts[pos]))
        list_elements.append(name)  # TODO: VERIFY HOW TO RETURN THE VALUE

    def analyze_bin_op_branch(self, node_visitor: ast.NodeVisitor, node: ast.BinOp, side: str, components: BinOpComponents):
        # 如果二元运算两侧的元素是函数调用  则需要进一步遍历调用函数节点（子树）
        subgraph = node_visitor.param_subgraph_init()
        subgraph.target_node = node_visitor.graph_info.tail if node_visitor.target_node is None else node_visitor.target_node
        value, _, _, _ = subgraph.visit(getattr(node, side))
        setattr(components, side, value)
        if value is not None and len(value) > 0:
            setattr(components, side, value[0])

    def extract_subscript_value(self, node_visitor: ast.NodeVisitor, node: ast.Subscript):
        return_types, file, name, base = node_visitor.visit_Call(cast(ast.Call, node.value)) # 嵌套访问函数调用（因为当前节点的子节点仍是函数调用节点）
        try:
            if name is not None and isinstance(name, str):
                call = get_calls(name)
                package = call if call.call_type else None
                name = package.return_types[0].full_path(), base
        finally:
            return name, base

    def analyze_attribute_value(self, node_visitor: ast.NodeVisitor, node: ast.Attribute,
                                components: AttributeComponents):
        subgraph = node_visitor.param_subgraph_init()
        subgraph.target_node = node_visitor.graph_info.tail if node_visitor.target_node is None else node_visitor.target_node
        return_types, file, _, base = subgraph.visit(node.value)
        node_visitor.graph_info.add_concurrent_flow(node_visitor.target_node)

        is_column = node_visitor._add_to_column(node.attr, base)

        if len(return_types) > 0:
            components.path = f"{return_types[0].library_path}.{return_types[0].name}{'' if is_column else f'.{node.attr}'}"
            components.parent_path = base
            components.file = file
        else:
            pass
            # print("ATTRIBUTE VALUE CALL: NO RETURN TYPE")


class List(AstPackage): # 列表
    def analyze_call_arguments(self, node_visitor: ast.NodeVisitor, node: ast.Call, components: CallArgumentsComponents,
                               call_components: CallComponents, pos: int):
        parameter_value = node_visitor.visit_List(cast(ast.List, node.args[pos]))
        for arg_list in parameter_value:
            node_visitor._add_to_column(arg_list, call_components.base_package)
            if isinstance(arg_list, str) and arg_list in node_visitor.files.keys():
                call_components.file = node_visitor.files.get(arg_list)

        return parameter_value

    def extract_assign_value(self, node_visitor: ast.NodeVisitor, node: ast.Assign, components: AssignComponents):
        components.value = node_visitor.visit_List(cast(ast.List, node.value))
        for element in components.value:
            node_visitor._extract_dataflow(element)

    def extract_keyword_value(self, node_visitor: ast.NodeVisitor, node: ast):
        return node_visitor.visit_List(node.value)

    def extract_list_element(self, node_visitor: ast.NodeVisitor, node: ast.List, pos: int,  list_elements: list):
        list_elements.append(node_visitor.visit_List(cast(ast.List, node.elts[pos])))


class Dict(AstPackage):  # 字典
    def analyze_call_arguments(self, node_visitor: ast.NodeVisitor, node: ast.Call, components: CallArgumentsComponents,
                               call_components: CallComponents, pos: int):
        return node_visitor.visit_Dict(cast(ast.Dict, node.args[pos]))

    def extract_assign_value(self, node_visitor: ast.NodeVisitor, node: ast.Assign, components: AssignComponents):
        components.value = node_visitor.visit_Dict(cast(ast.Dict, node.value))

    def extract_keyword_value(self, node_visitor: ast.NodeVisitor, node: ast):
        return node_visitor.visit_Dict(node.value)


class Subscript(AstPackage):  # 下标操作 如list[i]  value是被操作对象如list   slice是i（索引或切片）
    def analyze_call_arguments(self, node_visitor: ast.NodeVisitor, node: ast.Call, components: CallArgumentsComponents,
                               call_components: CallComponents, pos: int):
        arg_subscript, _ = node_visitor.visit_Subscript(cast(ast.Subscript, node.args[pos]))
        if isinstance(arg_subscript, list):
            return None

        arg_package = node_visitor.variables.get(arg_subscript, None)

        if isinstance(arg_package, Calls.Call):
            return arg_package.name
        return arg_package

    def extract_assign_value(self, node_visitor: ast.NodeVisitor, node: ast.Assign, components: AssignComponents):
        components.value, _ = node_visitor.visit_Subscript(cast(ast.Subscript, node.value))
        node_visitor._extract_dataflow(components.value)

        if isinstance(components.value, list):
            return

        components.variable = node_visitor.variables.get(components.value, None)
        if components.value in node_visitor.files.keys():
            components.file = node_visitor.files.get(components.value)
            node_visitor._connect_node_to_column(components.file)

    def analyze_assign_target(self, node_visitor: ast.NodeVisitor, node: ast, components: AssignComponents):
        variable, _ = node_visitor.visit_Subscript(node) # 访问左侧变量(由于是下标类型变量，所以要用嵌套访问下标元素的操作)
        node_visitor._extract_dataflow(variable)
        if isinstance(variable, str):
            node_visitor.data_flow_container[variable] = node_visitor.graph_info.tail
            file = node_visitor.files.get(variable)
            node_visitor._connect_node_to_column(file)

        return variable

    def extract_keyword_value(self, node_visitor: ast.NodeVisitor, node: ast):
        name, _ = node_visitor.visit_Subscript(node.value)
        return name

    def extract_list_element(self, node_visitor: ast.NodeVisitor, node: ast.List, pos: int,  list_elements: list):
        name, _ = node_visitor.visit_Subscript(cast(ast.Subscript, node.elts[pos]))
        list_elements.append(name)

    def analyze_bin_op_branch(self, node_visitor: ast.NodeVisitor, node: ast.BinOp, side: str, components: BinOpComponents):
        element_name, _ = node_visitor.visit_Subscript(getattr(node, side)) # 下标节点还需要进一步遍历
        element_package = node_visitor.variables.get(element_name, element_name)  # 获取下标对应的操作变量的信息
        setattr(components, side, element_package)

    def extract_subscript_value(self, node_visitor: ast.NodeVisitor, node: ast.Subscript):
        return node_visitor.visit_Subscript(cast(ast.Subscript, node.value)) # 嵌套访问下标（因为当前节点的子节点仍然是下标，可进一步递归访问）

    def analyze_attribute_value(self, node_visitor: ast.NodeVisitor, node: ast.Attribute,
                                components: AttributeComponents):
        value, _ = node_visitor.visit_Subscript(cast(ast.Subscript, node.value))
        components.path = f'{value}.{node.attr}'


class Lambda(AstPackage):  # 匿名函数
    def analyze_call_arguments(self, node_visitor: ast.NodeVisitor, node: ast.Call, components: CallArgumentsComponents,
                               call_components: CallComponents, pos: int):
        return format_node_text(node.args[pos])


class BinOp(AstPackage): # 二元运算
    def extract_assign_value(self, node_visitor: ast.NodeVisitor, node: ast.Assign, components: AssignComponents):
        components.value = node_visitor.visit_BinOp(cast(ast.BinOp, node.value))

    def extract_keyword_value(self, node_visitor: ast.NodeVisitor, node: ast):
        return node_visitor.visit_BinOp(node.value)

    def analyze_bin_op_branch(self, node_visitor: ast.NodeVisitor, node: ast.BinOp, side: str, components: BinOpComponents):
        setattr(components, side, node_visitor.visit_BinOp(getattr(node, side)))

    def analyze_attribute_value(self, node_visitor: ast.NodeVisitor, node: ast.Attribute,
                                components: AttributeComponents):
        values = node_visitor.visit_BinOp(cast(ast.BinOp, node.value))
        components.path = f"{values}.{node.attr}"


class Tuple(AstPackage): # 元组
    def extract_assign_value(self, node_visitor: ast.NodeVisitor, node: ast.Assign, components: AssignComponents):
        components.value = node_visitor.visit_Tuple(cast(ast.Tuple, node.value))

    def analyze_assign_target(self, node_visitor: ast.NodeVisitor, node: ast, components: AssignComponents):
        tuple_values = node_visitor.visit_Tuple(node)
        for el in tuple_values:
            node_visitor.data_flow_container[el] = node_visitor.graph_info.tail

        if components.value is not None and tuple_values is not None:
            for sub_target, package in tuple(zip(tuple_values, components.value)):
                node_visitor.variables[sub_target] = package
                if components.file is not None:
                    node_visitor.files[sub_target] = components.file

    def extract_keyword_value(self, node_visitor: ast.NodeVisitor, node: ast):
        return node_visitor.visit_Tuple(node.value)


class Compare(AstPackage):
    def analyze_bin_op_branch(self, node_visitor: ast.NodeVisitor, node: ast.BinOp, side: str, components: BinOpComponents):
        node_visitor.visit_Compare(getattr(node, side))


ast_packages = {
    ast.Name: Name(),
    ast.Attribute: Attribute(),
    ast.Constant: Constant(),
    ast.Call: Call(),
    ast.List: List(),
    ast.Dict: Dict(),
    ast.Subscript: Subscript(),
    ast.Lambda: Lambda(),
    ast.BinOp: BinOp(),
    ast.Tuple: Tuple(),
    ast.Compare: Compare(),
}


def get_ast_package(package: ast) -> AstPackage:   # 元素和处理方法映射
    return ast_packages.get(type(package), AstPackage())
