import inspect
import re
from typing import Dict, Optional
from multiprocessing import Manager, RLock, Lock
from . import CallType, Call

# 别名映射表
ALIAS_MAPPING = {
    # 基础库
    'pd': 'pandas',
    'np': 'numpy',
    'plt': 'matplotlib.pyplot',
    'json': 'json',
    'os': 'os',
    're': 're',
    'sys': 'sys',

    # 可视化库
    'sns': 'seaborn',
    'px': 'plotly.express',
    'go': 'plotly.graph_objects',
    'hv': 'holoviews',
    'bokeh': 'bokeh',

    # 机器学习库
    'tf': 'tensorflow',
    'xgb': 'xgboost',
    'lgbm': 'lightgbm',

    # 统计库
    'sm': 'statsmodels'
}

# 进程级共享资源：使用 Manager 创建跨进程共享的字典和锁
manager = Manager()
packages = manager.dict()  # 进程共享的缓存字典
FAILED_PATHS_STATS = manager.dict()  # 进程共享的统计字典
FAILED_PATHS_STATS["new_added_valid"] = 0
FAILED_PATHS_STATS["new_added_invalid"] = 0
FAILED_PATHS_STATS["new_added_unknown"] = 0

# 进程锁：确保跨进程互斥
cache_lock = RLock()  # 可重入进程锁（支持递归加锁）
stats_lock = Lock()   # 进程互斥锁（保护统计字典）


def _get_serializable_default(default_val) -> Optional[str]:
    """最小改动：将参数默认值转为可序列化的字符串描述（避免不可pickle对象）"""
    if default_val is inspect.Parameter.empty:
        return None
    # 模块对象：转为模块名（如 <module 'pandas'> → "pandas"）
    if inspect.ismodule(default_val):
        return f"module:{default_val.__name__}"
    # 类对象：转为 "模块.类名"（如 pandas.DataFrame → "pandas.core.frame.DataFrame"）
    elif inspect.isclass(default_val):
        return f"class:{default_val.__module__}.{default_val.__qualname__}"
    # 函数/方法对象：转为 "模块.函数名"
    elif inspect.isfunction(default_val) or inspect.ismethod(default_val):
        return f"func:{default_val.__module__}.{default_val.__qualname__}"
    # 基础类型（int/str/bool等）：直接转为字符串（可序列化）
    else:
        try:
            return str(default_val)
        except Exception:
            return "unknown:unserializable_value"


def _get_params_from_signature(obj) -> Dict[str, Optional[str]]:
    """从对象签名提取参数（仅修改：参数默认值用可序列化字符串描述）"""
    params = {}
    try:
        # 处理静态方法/类方法：需解包__func__获取签名
        if type(obj) in (staticmethod, classmethod):
            sig = obj.__signature__ if hasattr(obj, '__signature__') else inspect.signature(obj.__func__)
        else:
            sig = obj.__signature__ if hasattr(obj, '__signature__') else inspect.signature(obj)

        for param_name, param in sig.parameters.items():
            if param_name in ['self', 'cls', 'args', 'kwargs']:
                continue
            # 核心修改：用可序列化字符串替换原对象
            params[param_name] = _get_serializable_default(param.default)
    except (ValueError, TypeError, AttributeError):
        pass
    return params


def _cache_call(path: str, call_instance: Call) -> bool:
    """
    统一缓存工具函数：加锁保护，缓存 Call 实例到 packages
    :param path: 缓存的键（路径字符串）
    :param call_instance: 要缓存的 Call 实例
    :return: True=缓存成功（新写入），False=已存在（未重复缓存）
    """
    if not path or not call_instance:
        return False  # 路径为空或实例无效，不缓存
    
    with cache_lock:  # 多进程锁保护，确保原子性
        if path in packages:
            #print(f"[缓存已存在] {path}")
            return False  # 已缓存，无需重复写入
        packages[path] = call_instance
        #print(f"[缓存成功] {path} -> {call_instance.call_type}")
        return True


def _cache_middle_path(middle_path: str) -> None:
    """递归缓存中间路径（模块/类），调用统一缓存函数"""
    if not middle_path:
        return
    if middle_path in packages:  # 先快速判断（减少锁竞争）
        #print(f"[无需重复缓存] {middle_path}")
        return
    
    #print(f"[开始缓存中间路径] {middle_path}")
    parts = middle_path.split('.')
    name = parts[-1]
    parent_path = '.'.join(parts[:-1]) if len(parts) > 1 else ''

    try:
        # 导入中间路径对象
        if len(parts) == 1:
            obj = __import__(name)
        else:
            parent_module = __import__(parent_path, fromlist=[name])
            obj = getattr(parent_module, name)

        # 生成 Call 实例（仅缓存模块/类）
        mid_call = None
        if inspect.ismodule(obj):
            call_type = CallType.LIBRARY if not parent_path else CallType.PACKAGE
            mid_call = Call(name=name, library_path=parent_path, call_type=call_type)
        elif inspect.isclass(obj):
            params = _get_params_from_signature(obj.__init__) if hasattr(obj, '__init__') else {}
            mid_call = Call(name=name, library_path=parent_path, parameters=params, 
                           is_class_def=True, call_type=CallType.CLASS)
        else:
            #print(f"[非中间路径类型] {middle_path}（仅缓存模块/类）")
            return

        # 调用统一缓存函数，缓存成功则统计 valid
        if _cache_call(middle_path, mid_call):
            with stats_lock:
                FAILED_PATHS_STATS["new_added_valid"] += 1
            # 递归缓存父路径（确保父路径先于子路径缓存）
            _cache_middle_path(parent_path)

    except (ImportError, AttributeError) as e:
        #print(f"[中间路径缓存失败] {middle_path}：{str(e)}")
        return


def parse_path_meta(path: str) -> Optional[Call]:
    """解析路径元信息，生成 Call 实例"""
    #print(f"\n[开始解析] {path}")
    parts = path.split('.')
    name = parts[-1]
    parent_path = '.'.join(parts[:-1]) if len(parts) > 1 else ''

    try:
        # 缓存所有中间路径
        _cache_middle_path(path)

        # 导入目标对象
        if len(parts) == 1:
            obj = __import__(name)
        else:
            parent_module = __import__(parent_path, fromlist=[name])
            _cache_middle_path(parent_path)
            obj = getattr(parent_module, name)

    except (ImportError, AttributeError) as e:
        #print(f"[直接导入失败] {path}：{str(e)}")
        # 类内方法检查
        class_method_call = None
        if len(parts) >= 2 and parent_path:
            try:
                _cache_middle_path(parent_path)  # 确保父类路径已缓存
                class_parts = parent_path.split('.')
                class_module_str = '.'.join(class_parts[:-1])
                class_name = class_parts[-1]
                #print(f"[尝试解析类-方法] {parent_path}->{name}")

                class_module = __import__(class_module_str, fromlist=[class_name])
                class_obj = getattr(class_module, class_name)
                if inspect.isclass(class_obj) and hasattr(class_obj, name):
                    method_obj = getattr(class_obj, name)
                    if (inspect.ismethod(method_obj) or
                            inspect.isfunction(method_obj) or
                            inspect.isbuiltin(method_obj) or
                            type(method_obj) is staticmethod or
                            type(method_obj) is classmethod or
                            inspect.ismethoddescriptor(method_obj) or
                            (callable(method_obj) and not inspect.isclass(method_obj) and not inspect.ismodule(method_obj))):
                        parameters = _get_params_from_signature(method_obj)
                        return_types = [packages[parent_path]] if parent_path in packages else []
                        class_method_call = Call(
                            name=name,
                            library_path=parent_path,
                            parameters=parameters,
                            is_class_def=False,
                            call_type=CallType.FUNCTION,
                            return_types=return_types
                        )
                        # 调用统一缓存函数，缓存成功则统计 valid
                        if _cache_call(path, class_method_call):
                            with stats_lock:
                                FAILED_PATHS_STATS["new_added_valid"] += 1
                        #print(f"[类内方法解析成功] ")
                        return class_method_call
            except Exception as e2:
                #print(f"[类内方法检查失败] {path}：{str(e2)}")
                pass

        # 逐级向上尝试
        max_level = len(parts)
        base_module = None
        remaining_parts = []
        found = False
        #print("[开始逐级尝试...]")
        for level in range(max_level - 1, 0, -1):
            current_parent_path = '.'.join(parts[:level])
            try:
                base_module = __import__(current_parent_path, fromlist=[''])
                remaining_parts = parts[level:]
                found = True
                _cache_middle_path(current_parent_path)
                #print(f"[找到基础模块] {current_parent_path}")
                break
            except ImportError:
                continue

        if not found:
            with stats_lock:
                FAILED_PATHS_STATS[path] = f"无可用父模块"
                FAILED_PATHS_STATS["new_added_unknown"] += 1
            #print(f"[解析失败] {path}：无可用父模块")
            return Call()

        # 沿着基础模块向下追溯
        current_obj = base_module
        current_parent_path = '.'.join(parts[:level])
        final_call = None
        for i, part in enumerate(remaining_parts):
            try:
                current_obj = getattr(current_obj, part)
                current_full_path = f"{current_parent_path}.{part}" if current_parent_path else part
                _cache_middle_path(current_full_path)

                if (inspect.ismethod(current_obj) or
                        inspect.isfunction(current_obj) or
                        inspect.isbuiltin(current_obj) or
                        type(current_obj) is staticmethod or
                        type(current_obj) is classmethod or
                        inspect.ismethoddescriptor(current_obj) or
                        (callable(current_obj) and not inspect.isclass(current_obj) and not inspect.ismodule(current_obj))):
                    parameters = _get_params_from_signature(current_obj)
                    return_types = [packages[current_parent_path]] if current_parent_path in packages else []
                    final_call = Call(
                        name=part,
                        library_path=current_parent_path,
                        parameters=parameters,
                        is_class_def=False,
                        call_type=CallType.FUNCTION,
                        return_types=return_types
                    )
                    with stats_lock:
                        FAILED_PATHS_STATS["new_added_valid"] += 1
                    break
                elif inspect.isclass(current_obj):
                    if i == len(remaining_parts) - 1:
                        parameters = _get_params_from_signature(current_obj.__init__) if hasattr(current_obj, '__init__') else {}
                        final_call = Call(
                            name=part,
                            library_path=current_parent_path,
                            parameters=parameters,
                            is_class_def=True,
                            call_type=CallType.CLASS
                        )
                        with stats_lock:
                            FAILED_PATHS_STATS["new_added_valid"] += 1
                        break
                    else:
                        current_parent_path = current_full_path
                        continue
                elif inspect.ismodule(current_obj):
                    current_parent_path = current_full_path
                    continue
                else:
                    current_parent_path = current_full_path
                    continue
            except AttributeError as e3:
                #print(f"[追溯失败] {current_parent_path}.{part}：{str(e3)}")
                break

        if final_call:
            _cache_call(path, final_call)
            #print(f"[追溯成功] {path}：{final_call.call_type}")
            return final_call
        else:
            with stats_lock:
                FAILED_PATHS_STATS[path] = "追溯失败"
                FAILED_PATHS_STATS["new_added_unknown"] += 1
            #print(f"[解析失败] {path}：追溯失败")
            return Call(name=name, library_path=parent_path)

    # 处理直接导入成功的情况
    parameters = {}
    if (inspect.isfunction(obj) or
            inspect.ismethod(obj) or
            inspect.isbuiltin(obj) or
            type(obj) is staticmethod or
            type(obj) is classmethod or
            inspect.ismethoddescriptor(obj) or
            (callable(obj) and not inspect.isclass(obj) and not inspect.ismodule(obj))):
        try:
            sig = inspect.signature(obj.__func__) if type(obj) in (staticmethod, classmethod) else inspect.signature(obj)
            for param_name, param in sig.parameters.items():
                if param_name in ['self', 'cls']:
                    continue
                # 核心修改：用可序列化字符串替换原对象
                parameters[param_name] = _get_serializable_default(param.default)
        except (ValueError, TypeError):
            parameters = {}
    elif inspect.isclass(obj) and hasattr(obj, '__init__'):
        try:
            sig = inspect.signature(obj.__init__)
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                # 核心修改：用可序列化字符串替换原对象
                parameters[param_name] = _get_serializable_default(param.default)
        except (ValueError, TypeError):
            parameters = {}

    # 生成最终Call实例
    if (inspect.isfunction(obj) or
            inspect.ismethod(obj) or
            inspect.isbuiltin(obj) or
            type(obj) is staticmethod or
            type(obj) is classmethod or
            inspect.ismethoddescriptor(obj) or
            (callable(obj) and not inspect.isclass(obj) and not inspect.ismodule(obj))):
        with stats_lock:
            FAILED_PATHS_STATS["new_added_valid"] += 1
        return_types = [packages[parent_path]] if parent_path in packages else []
        final_call = Call(
            name=name,
            library_path=parent_path,
            parameters=parameters,
            is_class_def=False,
            call_type=CallType.FUNCTION,
            return_types=return_types
        )
    elif inspect.ismodule(obj):
        with stats_lock:
            FAILED_PATHS_STATS["new_added_valid"] += 1
        call_type = CallType.LIBRARY if not parent_path else CallType.PACKAGE
        final_call = Call(name=name, library_path=parent_path, call_type=call_type, return_types=[])
    elif inspect.isclass(obj) or (hasattr(obj, '__class__') and obj.__class__.__name__ == 'type'):
        with stats_lock:
            FAILED_PATHS_STATS["new_added_valid"] += 1
        final_call = Call(
            name=name,
            library_path=parent_path,
            parameters=parameters,
            is_class_def=True,
            call_type=CallType.CLASS
        )
    else:
        #print(f"[非预期类型] {path}")
        with stats_lock:
            FAILED_PATHS_STATS[path] = f"非预期类型（{type(obj)}）"
            FAILED_PATHS_STATS["new_added_unknown"] += 1
        final_call = Call(name=name, library_path=parent_path)

    # 缓存最终结果
    _cache_call(path, final_call)
    return final_call


def get_calls(package_name: str) -> Call:
    """对外接口：解析包路径并返回Call实例"""
    #print(f"\n=== 处理输入：{package_name} ===")
    cleaned_path = package_name.strip().strip('.')
    raw_path = package_name.strip()

    # 无效输入判断
    if not isinstance(package_name, str) or not cleaned_path:
        with stats_lock:
            FAILED_PATHS_STATS["new_added_invalid"] += 1
        #print(f"[无效输入] {package_name}：空或非字符串")
        return Call()
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*$', raw_path):
        with stats_lock:
            FAILED_PATHS_STATS["new_added_invalid"] += 1
        #print(f"[无效输入] {package_name}：格式不合法")
        return Call()

    # 别名替换
    parts = cleaned_path.split('.')
    if parts[0] in ALIAS_MAPPING:
        parts[0] = ALIAS_MAPPING[parts[0]]
        full_path = '.'.join(parts)
        #print(f"[别名替换] {cleaned_path} → {full_path}")
    else:
        full_path = cleaned_path

    # 缓存逻辑
    with cache_lock:
        if full_path in packages:
            #print(f"[命中缓存] {full_path}")
            return packages[full_path]

        parsed_call = parse_path_meta(full_path)

    return parsed_call